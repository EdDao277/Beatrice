"""Frozen localhost service for bounded pick-model scores and evidence counts."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "2")

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = ROOT / "scripts/benchmark"
if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))

import lightgbm as lgb
import numpy as np

from ml_features import FEATURE_NAMES, vector
from protocol import load_prepared
from readiness import FinalHistory
from recency_features import EXTENDED_NAMES, RecencyTable, extend
from saved_scenarios import evidence_for
from scaled_train import read, rows, sha
from temporal import EarlierHistory
from tree_ranker import tree_score


EXPECTED_MODEL_VERSION = "recency-2026-09-14"
EXPECTED_SCHEMA_VERSION = "beatrice-pick-recency-108-v1"
EXPECTED_MODEL_HASH = "ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5"
EXPECTED_FEATURE_COUNT = 108
MAX_BODY_BYTES = 64 * 1024
MAX_CANDIDATES = 200
MAX_PICKS_PER_SIDE = 5
MAX_SAFE_JSON_INTEGER = 2**53 - 1
_REQUEST_KEYS = {
    "requestId", "schemaVersion", "modelVersion", "modelSha256", "patch",
    "allyPicks", "enemyPicks", "candidateIds",
}
_PATCH = re.compile(r"^[0-9]{1,2}\.[0-9]{1,2}$")
_PLAYERS = tuple(f"saved:{index}" for index in range(5))


class RequestError(ValueError):
    """The caller did not satisfy the frozen JSON contract."""


def _utc_iso(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_day(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeError("Service clock must be timezone-aware")
    return value.astimezone(timezone.utc).date().isoformat()


def _require_text(value, *, maximum: int, field: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > maximum
            or value != value.strip() or any(ord(character) < 32 for character in value)):
        raise RequestError(f"Invalid {field}")
    return value


def _require_ids(value, *, maximum: int, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise RequestError(f"Invalid {field}")
    result = [_require_text(item, maximum=50, field=field) for item in value]
    if len(set(result)) != len(result):
        raise RequestError(f"Duplicate {field}")
    return result


def _validated_request(payload) -> dict:
    if not isinstance(payload, dict) or set(payload) != _REQUEST_KEYS:
        raise RequestError("Invalid request fields")
    request_id = _require_text(payload["requestId"], maximum=128, field="requestId")
    if payload["schemaVersion"] != EXPECTED_SCHEMA_VERSION:
        raise RequestError("Schema mismatch")
    if payload["modelVersion"] != EXPECTED_MODEL_VERSION:
        raise RequestError("Model mismatch")
    if payload["modelSha256"] != EXPECTED_MODEL_HASH:
        raise RequestError("Model hash mismatch")
    patch = _require_text(payload["patch"], maximum=16, field="patch")
    if not _PATCH.fullmatch(patch):
        raise RequestError("Invalid patch")
    allies = _require_ids(payload["allyPicks"], maximum=MAX_PICKS_PER_SIDE, field="allyPicks")
    enemies = _require_ids(payload["enemyPicks"], maximum=MAX_PICKS_PER_SIDE, field="enemyPicks")
    candidates = _require_ids(payload["candidateIds"], maximum=MAX_CANDIDATES, field="candidateIds")
    visible = allies + enemies
    if len(set(visible)) != len(visible) or set(visible) & set(candidates):
        raise RequestError("Champion IDs must be distinct")
    return {
        "requestId": request_id,
        "schemaVersion": EXPECTED_SCHEMA_VERSION,
        "modelVersion": EXPECTED_MODEL_VERSION,
        "modelSha256": EXPECTED_MODEL_HASH,
        "patch": patch,
        "allyPicks": allies,
        "enemyPicks": enemies,
        "candidateIds": candidates,
    }


def _verify_file(path: Path, expected: str) -> None:
    if path.name in ("", ".", "..") or sha(path) != expected:
        raise ValueError(f"Frozen artifact changed: {path.name}")


class RankService:
    """Builds reviewed features and serializes access to the frozen predictor."""

    def __init__(
        self,
        *,
        model,
        games: list[dict],
        audited_games: list[dict],
        training_seen: set[str],
        clock: Callable[[], datetime] | None = None,
        history_identity: dict | None = None,
    ):
        if model.num_feature() != EXPECTED_FEATURE_COUNT:
            raise ValueError("Frozen model feature count mismatch")
        if len(EXTENDED_NAMES) != EXPECTED_FEATURE_COUNT or len(FEATURE_NAMES) != 33:
            raise ValueError("Frozen feature schema mismatch")
        if not games or not audited_games:
            raise ValueError("Professional history is empty")
        if any(not isinstance(champion, str) or not champion for champion in training_seen):
            raise ValueError("Invalid training exposure set")
        self._model = model
        self.provenance = history_identity or {
            'historyBundleVersion': 'fixture', 'historyBundleSha256': '0' * 64,
        }
        self._history = EarlierHistory(games)
        self._recency = FinalHistory(audited_games)
        self._known_patches = tuple(sorted({game["patch"] for game in audited_games}))
        self._training_seen = frozenset(training_seen)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._warmed_day = None
        self._snapshot = None
        self._tables = {}
        self._unknown_table = None
        self.warm()

    def is_ready(self) -> bool:
        try:
            day = _utc_day(self._clock())
        except Exception:
            return False
        return self._ready.is_set() and self._warmed_day == day and self._snapshot is not None

    def warm(self) -> None:
        """Prepare one UTC day's immutable request state outside the latency budget."""
        day = _utc_day(self._clock())
        self._ready.clear()
        with self._lock:
            self._warmed_day = None
            snapshot = self._history.advance(day)
            if snapshot["latestObservation"] is None:
                raise RuntimeError("No lagged history is available")
            tables = {patch: self._recency.at(day, patch) for patch in self._known_patches}
            reference = next(iter(tables.values()))
            unknown = RecencyTable(
                [reference.windows[0], reference.windows[1], (0, Counter(), Counter())],
                source_count=reference.source_count,
            )
            probe = np.asarray(
                tree_score(self._model, np.zeros((1, EXPECTED_FEATURE_COUNT), dtype=np.float32)),
                dtype=float,
            )
            if probe.shape != (1,) or not np.isfinite(probe).all():
                raise RuntimeError("Frozen model warmup failed")
            self._snapshot = snapshot
            self._tables = tables
            self._unknown_table = unknown
            self._warmed_day = day
            self._ready.set()

    @classmethod
    def load(
        cls,
        *,
        prepared_dir: Path,
        compact_dir: Path,
        model_dir: Path,
        clock: Callable[[], datetime] | None = None,
        history_bundle: Path | None = None,
        history_hash: str | None = None,
    ) -> "RankService":
        prepared_dir, compact_dir, model_dir = map(Path, (prepared_dir, compact_dir, model_dir))
        model_manifest = read(model_dir / "manifest.json")
        protocol = read(model_dir / "protocol.json")
        compact_manifest = read(compact_dir / "manifest.json")
        model_path = model_dir / "recency_tree.txt"

        if model_manifest.get("status") != "COMPLETE_OFFLINE_BLIND_EXPERIMENT":
            raise ValueError("Frozen model manifest is incomplete")
        for name in ("recency_tree.txt", "protocol.json"):
            expected = model_manifest.get("artifacts", {}).get(name)
            if not isinstance(expected, str):
                raise ValueError("Frozen model manifest is incomplete")
            _verify_file(model_dir / name, expected)
        if sha(model_path) != EXPECTED_MODEL_HASH:
            raise ValueError("Frozen model hash mismatch")
        if (protocol.get("features") != list(EXTENDED_NAMES)
                or protocol.get("datasetManifestSha256") != sha(compact_dir / "manifest.json")
                or model_manifest.get("datasetManifestSha256") != sha(compact_dir / "manifest.json")):
            raise ValueError("Frozen feature schema or lineage mismatch")

        for name in ("ml_features.py", "recency_features.py", "tree_ranker.py"):
            expected = model_manifest.get("codeSha256", {}).get(name)
            if not isinstance(expected, str):
                raise ValueError("Frozen feature source manifest is incomplete")
            _verify_file(BENCHMARK_DIR / name, expected)
        for name in ("baseline.py", "protocol.py", "temporal.py"):
            expected = compact_manifest.get("codeSha256", {}).get(name)
            if not isinstance(expected, str):
                raise ValueError("Frozen history source manifest is incomplete")
            _verify_file(BENCHMARK_DIR / name, expected)
        for name in ("source-audit.jsonl.gz", "contexts.jsonl.gz"):
            expected = compact_manifest.get("artifacts", {}).get(name)
            if not isinstance(expected, str):
                raise ValueError("Frozen history manifest is incomplete")
            _verify_file(compact_dir / name, expected)

        games, provenance = load_prepared(prepared_dir)
        expected_input = compact_manifest.get("input", {})
        if (provenance["gamesSha256"] != expected_input.get("gamesSha256")
                or provenance["reportSha256"] != expected_input.get("reportSha256")):
            raise ValueError("Professional history lineage mismatch")
        audit = {row["gameId"]: row for row in rows(compact_dir, "source-audit")}
        if set(audit) != {game["gameId"] for game in games}:
            raise ValueError("Professional history audit boundary mismatch")
        audited_games = [game for game in games if audit[game["gameId"]].get("eligible") is True]

        training_dates = [row["date"] for row in rows(compact_dir, "contexts") if row.get("split") == "training"]
        if not training_dates:
            raise ValueError("Frozen training exposure is unavailable")
        training_cutoff = datetime.fromisoformat(max(training_dates)[:10]) - timedelta(days=1)
        training_seen = {
            player["championId"]
            for game in games
            if datetime.fromisoformat(game["date"]) < training_cutoff
            for team in game["teams"]
            for player in team["players"]
        }

        identity = {'historyBundleVersion': 'frozen-prepared-20260908',
                    'historyBundleSha256': provenance['gamesSha256']}
        # Training exposure is deliberately computed above from frozen inputs only.
        if history_bundle is not None:
            from history_bundle import validate_bundle
            games, audited_games, identity = validate_bundle(history_bundle, games, audit, history_hash)
        model = lgb.Booster(model_file=str(model_path))
        if model.num_feature() != EXPECTED_FEATURE_COUNT:
            raise ValueError("Frozen model feature count mismatch")
        return cls(
            model=model,
            games=games,
            audited_games=audited_games,
            training_seen=training_seen,
            clock=clock,
            history_identity=identity,
        )

    def rank(self, payload) -> dict:
        request = _validated_request(payload)
        day = _utc_day(self._clock())
        ids = request["candidateIds"]
        context = {
            "playerIds": list(_PLAYERS),
            "allyPicks": request["allyPicks"],
            "enemyPicks": request["enemyPicks"],
        }

        if not self.is_ready() or not self._lock.acquire(blocking=False):
            raise RuntimeError("UTC day requires maintenance warmup")
        try:
            if not self._ready.is_set() or self._warmed_day != day or self._snapshot is None:
                raise RuntimeError("UTC day requires maintenance warmup")
            snapshot = self._snapshot
            table = self._tables.get(request["patch"], self._unknown_table)
            history = self._history.history
            original = np.asarray(
                [vector(context, evidence_for(history, champion, request["allyPicks"], _PLAYERS))
                 for champion in ids],
                dtype=np.float32,
            ).reshape(-1, len(FEATURE_NAMES))
            features = extend(original, ids, context, table)
            values = np.asarray(tree_score(self._model, features), dtype=float)
            if values.shape != (len(ids),) or not np.isfinite(values).all():
                raise RuntimeError("Frozen model returned invalid scores")

            scores = []
            for champion, value in zip(ids, values):
                recency = table.vector(champion)
                global_games = int(history.champions.get(champion, (0, 0))[0])
                recent_picks = int(round(math.expm1(recency[11])))
                patch_games = int(round(math.expm1(recency[21])))
                if not (0 <= recent_picks <= global_games <= MAX_SAFE_JSON_INTEGER
                        and 0 <= patch_games <= MAX_SAFE_JSON_INTEGER):
                    raise RuntimeError("Invalid evidence counts")
                scores.append({
                    "championId": champion,
                    "score": float(value),
                    "globalGames": global_games,
                    "recent30Picks": recent_picks,
                    "patchGames": patch_games,
                    "seenInTrainingHistory": champion in self._training_seen,
                })
        finally:
            self._lock.release()

        return {
            "requestId": request["requestId"],
            "schemaVersion": EXPECTED_SCHEMA_VERSION,
            "modelVersion": EXPECTED_MODEL_VERSION,
            "modelSha256": EXPECTED_MODEL_HASH,
            "patch": request["patch"],
            "evidenceCutoff": _utc_iso(snapshot["exclusiveCutoff"]),
            "historyLatest": _utc_iso(snapshot["latestObservation"]),
            **self.provenance,
            "historySnapshotId": snapshot["snapshotId"],
            "scores": scores,
        }


class _LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(BaseHTTPRequestHandler):
    server_version = "BeatricePickService"
    sys_version = ""

    def log_message(self, _format, *_args):
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            self._json(404, {"error": "not_found"})
            return
        if not self.server.rank_service.is_ready():
            self._json(503, {"status": "not_ready"})
            return
        self._json(200, {
            "status": "ready",
            **self.server.rank_service.provenance,
            "schemaVersion": EXPECTED_SCHEMA_VERSION,
            "modelVersion": EXPECTED_MODEL_VERSION,
            "modelSha256": EXPECTED_MODEL_HASH,
        })

    def do_POST(self):
        if self.path != "/rank":
            self._json(404, {"error": "not_found"})
            return
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            self._json(415, {"error": "unsupported_media_type"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._json(411, {"error": "length_required"})
            return
        if length <= 0:
            self._json(400, {"error": "invalid_request"})
            return
        if length > MAX_BODY_BYTES:
            self._json(413, {"error": "payload_too_large"})
            return
        try:
            raw = self.rfile.read(length)

            def reject_constant(_value):
                raise ValueError("Nonfinite JSON value")

            payload = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._json(400, {"error": "invalid_request"})
            return
        try:
            result = self.server.rank_service.rank(payload)
        except RequestError:
            self._json(400, {"error": "invalid_request"})
            return
        except Exception:
            self._json(500, {"error": "request_failed"})
            return
        self._json(200, result)

    def do_OPTIONS(self):
        self._json(405, {"error": "method_not_allowed"})


def create_server(rank_service: RankService, *, port: int = 8766) -> ThreadingHTTPServer:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Invalid port")
    if not rank_service.is_ready():
        raise RuntimeError("Rank service is not warm for the current UTC day")
    server = _LoopbackServer(("127.0.0.1", port), _Handler)
    server.rank_service = rank_service
    return server


def start_maintenance(
    rank_service: RankService,
    *,
    stop_event: threading.Event,
    interval_seconds: float = 1.0,
) -> threading.Thread:
    """Warm a rolled-over UTC day off the HTTP request threads."""
    if not isinstance(stop_event, threading.Event) or not math.isfinite(interval_seconds) or interval_seconds <= 0:
        raise ValueError("Invalid maintenance configuration")

    def maintain():
        while not stop_event.is_set():
            if hasattr(rank_service, 'refresh'):
                rank_service.refresh()
            if not rank_service.is_ready():
                try:
                    rank_service.warm()
                except Exception:
                    # Readiness stays false; retry without exposing internals over HTTP.
                    pass
            stop_event.wait(interval_seconds)

    thread = threading.Thread(target=maintain, name="pick-service-maintenance", daemon=True)
    thread.start()
    return thread


def serve(rank_service: RankService, *, port: int = 8766) -> None:
    """Run persistently on literal IPv4 loopback until interrupted."""
    server = create_server(rank_service, port=port)
    stop = threading.Event()
    maintenance = start_maintenance(rank_service, stop_event=stop)
    try:
        server.serve_forever()
    finally:
        stop.set()
        maintenance.join(timeout=2)
        server.server_close()


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Frozen localhost pick ranking service")
    parser.add_argument("--port", type=_port, default=8766)
    parser.add_argument("--prepared-dir", type=Path,
                        default=ROOT / "data/oracle/prepared-2026-09-08-reviewed")
    parser.add_argument("--compact-dir", type=Path,
                        default=ROOT / "data/oracle/compact-2026-09-11-resumable")
    parser.add_argument("--model-dir", type=Path,
                        default=ROOT / "data/oracle/blind-2026-09-14-reviewed")
    parser.add_argument("--history-pointer", type=Path,
                        default=ROOT / 'data/oracle/history-bundles/active.json')
    args = parser.parse_args(argv)
    from history_bundle import HistoryManager
    service = HistoryManager(lambda path, expected: RankService.load(
        prepared_dir=args.prepared_dir, compact_dir=args.compact_dir,
        model_dir=args.model_dir, history_bundle=path, history_hash=expected,
    ), args.history_pointer)
    serve(service, port=args.port)


if __name__ == "__main__":
    main()
