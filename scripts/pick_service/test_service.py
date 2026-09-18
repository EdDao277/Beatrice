"""Contract tests for the frozen loopback pick-ranking service."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from time import monotonic
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

SERVICE_DIR = Path(__file__).resolve().parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

try:
    from service import (
        EXPECTED_MODEL_HASH,
        EXPECTED_MODEL_VERSION,
        EXPECTED_SCHEMA_VERSION,
        MAX_BODY_BYTES,
        RankService,
        RequestError,
        create_server,
    )
except ImportError:
    EXPECTED_MODEL_HASH = EXPECTED_MODEL_VERSION = EXPECTED_SCHEMA_VERSION = None
    MAX_BODY_BYTES = 64 * 1024
    RankService = RequestError = create_server = None

try:
    from service import start_maintenance
except ImportError:
    start_maintenance = None


def game(identity, date, patch="16.17", blue_pick="A", red_pick="B"):
    def team(side, result, champion):
        picks = [champion, f"{side}2", f"{side}3", f"{side}4", f"{side}5"]
        return {
            "side": side,
            "result": result,
            "picks": picks,
            "bans": [f"{side}Ban"],
            "players": [
                {"playerId": f"{side}-p{i}", "championId": picked}
                for i, picked in enumerate(picks)
            ],
        }

    return {
        "gameId": identity,
        "date": date,
        "patch": patch,
        "teams": [team("BLUE", 1, blue_pick), team("RED", 0, red_pick)],
    }


class CapturingModel:
    def __init__(self, scores=None, width=108):
        self.scores = scores
        self.width = width
        self.last_x = None
        self.calls = []

    def num_feature(self):
        return self.width

    def predict(self, x, **_kwargs):
        self.last_x = x.copy()
        self.calls.append(x.copy())
        if self.scores is None:
            return np.arange(len(x), dtype=float) + 0.25
        if len(x) == 1 and len(self.scores) != 1:
            return np.zeros(1, dtype=float)
        return np.asarray(self.scores, dtype=float)


class ExplodingModel(CapturingModel):
    def predict(self, x, **_kwargs):
        if not self.calls:
            self.calls.append(x.copy())
            return np.zeros(len(x), dtype=float)
        raise ValueError("private model failure detail")


class MutableClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def payload(candidate_ids=None):
    return {
        "requestId": "request-123",
        "schemaVersion": EXPECTED_SCHEMA_VERSION,
        "modelVersion": EXPECTED_MODEL_VERSION,
        "modelSha256": EXPECTED_MODEL_HASH,
        "patch": "16.17",
        "allyPicks": ["ALLY"],
        "enemyPicks": ["ENEMY"],
        "candidateIds": candidate_ids if candidate_ids is not None else ["A", "C", "D"],
    }


def tiny_service(model=None, clock=None):
    history = [
        game("old", "2026-08-20 10:00:00"),
        game("included", "2026-09-12 20:15:30", blue_pick="ALLY", red_pick="C"),
        game("lagged", "2026-09-13 01:00:00", blue_pick="D", red_pick="E"),
    ]
    return RankService(
        model=model or CapturingModel(),
        games=history,
        audited_games=history,
        training_seen={"A", "C"},
        clock=clock or (lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc)),
    )


class RankServiceTests(unittest.TestCase):
    def test_response_identifies_bundle_and_exact_daily_snapshot(self):
        service = tiny_service()
        result = service.rank(payload())
        self.assertRegex(result['historyBundleSha256'], r'^[a-f0-9]{64}$')
        self.assertTrue(result['historyBundleVersion'])
        self.assertEqual(result['historySnapshotId'], service._snapshot['snapshotId'])

    def test_construction_warms_history_known_patches_and_model_before_requests(self):
        """Catches expensive history/table/model initialization leaking into first rank."""
        model = CapturingModel([3.5, -1.25, 0.0])
        service = tiny_service(model)
        self.assertTrue(service.is_ready())
        self.assertEqual(model.calls[0].shape, (1, 108))

        def cold_path(_value):
            raise AssertionError("request attempted cold history/table construction")

        service._history.advance = cold_path
        service._recency.at = lambda _day, _patch: cold_path(_patch)
        known = service.rank(payload())
        self.assertEqual([row["score"] for row in known["scores"]], [3.5, -1.25, 0.0])

        unknown_request = payload(["A"])
        unknown_request["patch"] = "99.99"
        unknown = service.rank(unknown_request)
        self.assertEqual(unknown["scores"][0]["recent30Picks"], 1)
        self.assertEqual(unknown["scores"][0]["patchGames"], 0)
        self.assertEqual(model.last_x[0, 41], .5)  # one A pick across two 30-day games
        self.assertAlmostEqual(model.last_x[0, 46], math.log1p(2))
        self.assertEqual(model.last_x[0, 49:57].tolist(), [0., 0., 0., 0., 0., 0., 1., 1.])

    def test_day_rollover_fails_fast_until_maintenance_warmup(self):
        """Catches a new UTC day rebuilding multi-year history in an interactive request."""
        clock = MutableClock(datetime(2026, 9, 14, 12, tzinfo=timezone.utc))
        service = tiny_service(clock=clock)
        self.assertTrue(service.is_ready())
        clock.value = datetime(2026, 9, 15, 0, 1, tzinfo=timezone.utc)
        self.assertFalse(service.is_ready())
        with self.assertRaises(RuntimeError):
            service.rank(payload())
        service.warm()
        self.assertTrue(service.is_ready())
        self.assertEqual(service.rank(payload())["evidenceCutoff"], "2026-09-14T00:00:00Z")

    def test_rank_preserves_requested_ids_and_builds_finite_108_feature_rows(self):
        """Catches reordered/dropped candidates and divergence from the frozen feature width."""
        self.assertIsNotNone(RankService)
        model = CapturingModel([3.5, -1.25, 0.0])
        result = tiny_service(model).rank(payload())

        self.assertEqual([row["championId"] for row in result["scores"]], ["A", "C", "D"])
        self.assertEqual([row["score"] for row in result["scores"]], [3.5, -1.25, 0.0])
        self.assertEqual(model.last_x.shape, (3, 108))
        self.assertTrue(np.isfinite(model.last_x).all())
        self.assertEqual(result["evidenceCutoff"], "2026-09-13T00:00:00Z")
        self.assertEqual(result["historyLatest"], "2026-09-12T20:15:30Z")
        self.assertEqual(
            {key: result[key] for key in ("requestId", "schemaVersion", "modelVersion", "modelSha256", "patch")},
            {key: payload()[key] for key in ("requestId", "schemaVersion", "modelVersion", "modelSha256", "patch")},
        )
        self.assertEqual(
            [{key: row[key] for key in ("globalGames", "recent30Picks", "patchGames", "seenInTrainingHistory")}
             for row in result["scores"]],
            [
                {"globalGames": 1, "recent30Picks": 1, "patchGames": 2, "seenInTrainingHistory": True},
                {"globalGames": 1, "recent30Picks": 1, "patchGames": 2, "seenInTrainingHistory": True},
                {"globalGames": 0, "recent30Picks": 0, "patchGames": 2, "seenInTrainingHistory": False},
            ],
        )

    def test_wrong_schema_or_hash_and_extra_identity_fields_are_rejected(self):
        """Catches accepting a caller with a different frozen contract or private player data."""
        service = tiny_service()
        for key, value in (
            ("schemaVersion", "other-schema"),
            ("modelVersion", "other-model"),
            ("modelSha256", "0" * 64),
        ):
            bad = payload()
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(RequestError):
                service.rank(bad)
        extra = payload()
        extra["playerIds"] = ["private-player"]
        with self.assertRaises(RequestError):
            service.rank(extra)

    def test_duplicate_ids_invalid_shapes_and_nonfinite_scores_fail_closed(self):
        """Catches ambiguous sets, excessive payloads, malformed types and NaN model output."""
        service = tiny_service()
        invalid = [
            payload(["A", "A"]),
            {**payload(), "candidateIds": [f"C{i}" for i in range(201)]},
            {**payload(), "allyPicks": ["A", "A"]},
            {**payload(), "candidateIds": ["ALLY"]},
            {**payload(), "patch": "not-a-patch"},
            {**payload(), "requestId": ""},
        ]
        for index, bad in enumerate(invalid):
            with self.subTest(index=index), self.assertRaises(RequestError):
                service.rank(bad)

        with self.assertRaises(RuntimeError):
            tiny_service(CapturingModel([float("nan"), 0.0, 1.0])).rank(payload())
        with self.assertRaises(ValueError):
            RankService(
                model=CapturingModel(width=107),
                games=[game("old", "2026-08-01 10:00:00")],
                audited_games=[game("old", "2026-08-01 10:00:00")],
                training_seen=set(),
                clock=lambda: datetime(2026, 9, 14, tzinfo=timezone.utc),
            )


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(tiny_service(), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path="/rank", body=None, content_type="application/json"):
        request = Request(
            self.base + path,
            data=body,
            headers={"Content-Type": content_type},
            method="POST" if body is not None else "GET",
        )
        try:
            response = urlopen(request, timeout=2)
            return response.status, dict(response.headers), json.loads(response.read())
        except HTTPError as error:
            return error.code, dict(error.headers), json.loads(error.read())

    def test_server_binds_literal_loopback_and_has_ready_health_without_cors(self):
        """Catches accidental LAN exposure and permissive browser access."""
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, headers, result = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "ready")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_server_refuses_unready_service_and_health_expires_at_day_rollover(self):
        """Catches binding or advertising readiness before the maintained day is warm."""
        class NotReady:
            def is_ready(self):
                return False

        with self.assertRaises(RuntimeError):
            create_server(NotReady(), port=0)

        clock = MutableClock(datetime(2026, 9, 14, 12, tzinfo=timezone.utc))
        rollover_service = tiny_service(clock=clock)
        rollover_server = create_server(rollover_service, port=0)
        rollover_thread = threading.Thread(target=rollover_server.serve_forever, daemon=True)
        rollover_thread.start()
        try:
            clock.value = datetime(2026, 9, 15, 0, 1, tzinfo=timezone.utc)
            base = f"http://127.0.0.1:{rollover_server.server_address[1]}"
            try:
                urlopen(base + "/health", timeout=2)
                self.fail("Stale-day health remained ready")
            except HTTPError as error:
                self.assertEqual(error.code, 503)
                self.assertEqual(json.loads(error.read()), {"status": "not_ready"})
        finally:
            rollover_server.shutdown()
            rollover_server.server_close()
            rollover_thread.join(timeout=2)

    def test_background_maintenance_recovers_rollover_while_http_stays_fail_closed(self):
        """Catches persistent serve remaining permanently stale after UTC rollover."""
        self.assertIsNotNone(start_maintenance)
        clock = MutableClock(datetime(2026, 9, 14, 12, tzinfo=timezone.utc))
        service = tiny_service(clock=clock)
        server = create_server(service, port=0)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        entered, release, stop = threading.Event(), threading.Event(), threading.Event()
        original_warm = service.warm

        def held_warm():
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test warmup release timed out")
            original_warm()

        service.warm = held_warm
        maintenance = start_maintenance(service, stop_event=stop, interval_seconds=.01)
        try:
            clock.value = datetime(2026, 9, 15, 0, 1, tzinfo=timezone.utc)
            self.assertTrue(entered.wait(1), "maintenance did not detect UTC rollover")

            with self.assertRaises(HTTPError) as health_error:
                urlopen(base + "/health", timeout=1)
            self.assertEqual(health_error.exception.code, 503)
            self.assertEqual(json.loads(health_error.exception.read()), {"status": "not_ready"})

            request = Request(
                base + "/rank",
                data=json.dumps(payload()).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as rank_error:
                urlopen(request, timeout=1)
            self.assertEqual(rank_error.exception.code, 500)
            self.assertEqual(json.loads(rank_error.exception.read()), {"error": "request_failed"})

            release.set()
            deadline = monotonic() + 2
            while not service.is_ready() and monotonic() < deadline:
                stop.wait(.01)
            self.assertTrue(service.is_ready(), "maintenance did not publish the new UTC day")
            response = urlopen(base + "/health", timeout=1)
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["status"], "ready")
        finally:
            release.set()
            stop.set()
            maintenance.join(timeout=2)
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)

    def test_http_requires_json_bounds_body_and_returns_only_generic_errors(self):
        """Catches unbounded reads, content-type drift and exception disclosure."""
        encoded = json.dumps(payload()).encode()
        status, _headers, result = self.request(body=encoded, content_type="text/plain")
        self.assertEqual((status, result), (415, {"error": "unsupported_media_type"}))

        status, _headers, result = self.request(body=b"{broken")
        self.assertEqual((status, result), (400, {"error": "invalid_request"}))

        huge = Request(
            self.base + "/rank",
            data=b"x",
            headers={"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)},
            method="POST",
        )
        try:
            urlopen(huge, timeout=2)
            self.fail("Oversized body was accepted")
        except HTTPError as error:
            self.assertEqual(error.code, 413)
            self.assertEqual(json.loads(error.read()), {"error": "payload_too_large"})

        self.server.rank_service = tiny_service(CapturingModel([float("nan"), 0.0, 1.0]))
        status, _headers, result = self.request(body=encoded)
        self.assertEqual((status, result), (500, {"error": "request_failed"}))
        self.assertNotIn("nan", json.dumps(result).lower())

        self.server.rank_service = tiny_service(ExplodingModel())
        status, _headers, result = self.request(body=encoded)
        self.assertEqual((status, result), (500, {"error": "request_failed"}))
        self.assertNotIn("private", json.dumps(result).lower())


class SavedScenarioParityTests(unittest.TestCase):
    def test_context_artifact_is_hash_verified_before_training_exposure_is_read(self):
        """Catches training_seen being derived from unverified context bytes."""
        root = SERVICE_DIR.parents[1]
        source = root / "data/oracle/compact-2026-09-11-resumable"
        with tempfile.TemporaryDirectory() as directory:
            compact = Path(directory)
            for name in ("manifest.json", "source-audit.jsonl.gz", "contexts.jsonl.gz"):
                shutil.copy2(source / name, compact / name)
            corrupt = bytearray((compact / "contexts.jsonl.gz").read_bytes())
            corrupt[-1] ^= 1
            (compact / "contexts.jsonl.gz").write_bytes(corrupt)
            with self.assertRaisesRegex(ValueError, "contexts.jsonl.gz"):
                RankService.load(
                    prepared_dir=root / "data/oracle/prepared-2026-09-08-reviewed",
                    compact_dir=compact,
                    model_dir=root / "data/oracle/blind-2026-09-14-reviewed",
                    clock=lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
                )

    def test_fixed_day_scores_and_evidence_match_saved_scenario_vectors(self):
        """Catches any live-adapter drift from the already-reviewed saved-scenario path."""
        root = SERVICE_DIR.parents[1]
        scenario_path = root / "data/oracle/saved-team-readiness/scenarios.json"
        observation_path = root / "data/oracle/saved-team-readiness/observations.json"
        if not scenario_path.exists() or not observation_path.exists():
            self.skipTest("Reviewed saved-scenario artifacts are unavailable")

        scenarios = json.loads(scenario_path.read_text(encoding="utf-8"))
        observations = json.loads(observation_path.read_text(encoding="utf-8"))
        scenario, observation = scenarios[0], observations[0]
        service = RankService.load(
            prepared_dir=root / "data/oracle/prepared-2026-09-08-reviewed",
            compact_dir=root / "data/oracle/compact-2026-09-11-resumable",
            model_dir=root / "data/oracle/blind-2026-09-14-reviewed",
            clock=lambda: datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        )
        ids = [row["id"] for row in observation["java"]]
        request = payload(ids)
        request["allyPicks"] = scenario["allies"]
        request["enemyPicks"] = scenario["enemies"]
        response = service.rank(request)

        actual = {row["championId"]: row for row in response["scores"]}
        for champion in ids:
            with self.subTest(champion=champion):
                self.assertAlmostEqual(actual[champion]["score"], observation["scores"][champion], places=12)
                self.assertEqual(
                    {key: actual[champion][key] for key in
                     ("globalGames", "recent30Picks", "patchGames", "seenInTrainingHistory")},
                    {key: observation["support"][champion][key] for key in
                     ("globalGames", "recent30Picks", "patchGames", "seenInTrainingHistory")},
                )
        self.assertEqual(response["historyLatest"], "2026-09-07T22:42:48Z")


if __name__ == "__main__":
    unittest.main()
