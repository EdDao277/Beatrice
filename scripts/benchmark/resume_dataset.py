"""Checkpoint compact exports in independently verified game shards (Windows spawn safe)."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
import gzip
import hashlib
import json
import multiprocessing
from pathlib import Path
import shutil
from uuid import uuid4

import compact_dataset as compact
from evaluate import line, sample_indices, write_json
from source_audit import audit_sources
from temporal import dataset_partitions

SPLITS = ('training', 'validation')
ARTIFACTS = {name + '.jsonl.gz' for name in (
    'contexts', 'labels', 'features', 'evidence', 'snapshots', 'source-audit', 'exclusions', 'timings')}
ARTIFACTS.update(('feature-schema.json', 'splits.json', 'report.json'))
_AUDITED = None


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path, name):
    with gzip.open(path / (name + '.jsonl.gz'), 'rt', encoding='utf-8') as stream:
        for row in stream:
            yield json.loads(row)


def verify(path):
    manifest = read(path / 'manifest.json')
    if manifest.get('version') != 3 or set(manifest['artifacts']) != ARTIFACTS:
        raise ValueError('Invalid shard artifact contract')
    for name, expected in manifest['artifacts'].items():
        if compact.file_hash(path / name) != expected:
            raise ValueError('Shard hash mismatch: ' + str(path / name))
    return manifest


def initialize(audited):
    global _AUDITED
    _AUDITED = audited


def export_shard(prepared, raw_dir, path, selected):
    compact.build(prepared, raw_dir, path, _selected_game_ids=selected, _audited=_AUDITED)
    return path


def current_inputs(prepared, raw_dir, provenance):
    paths = [prepared / 'games.jsonl', prepared / 'report.json']
    paths.extend(raw_dir / source['filename'] for source in provenance['rawSources'])
    return {str(path.resolve()): compact.file_hash(path) for path in paths}


def merge(shards, output, selected, audited):
    """Stream case artifacts; combine counts, never average per-shard rates."""
    manifests = [verify(path) for path in shards]
    first = manifests[0]
    for manifest in manifests[1:]:
        if {k: v for k, v in manifest.items() if k not in ('artifacts', 'selectedGames')} != {
                k: v for k, v in first.items() if k not in ('artifacts', 'selectedGames')}:
            raise ValueError('Shard manifests disagree')
    output.mkdir()
    for name in ('splits.json', 'feature-schema.json', 'source-audit.jsonl.gz'):
        if len({m['artifacts'][name] for m in manifests}) != 1:
            raise ValueError('Shard source/schema mismatch')
        shutil.copyfile(shards[0] / name, output / name)
    with ExitStack() as stack:
        streams = {name: compact.compressed_stream(stack, output / (name + '.jsonl.gz'))
                   for name in ('contexts', 'labels', 'features', 'evidence', 'timings', 'snapshots', 'exclusions')}
        for name in ('contexts', 'labels', 'features', 'evidence', 'timings'):
            seen = set()
            for shard in shards:
                for row in rows(shard, name):
                    if row['caseId'] in seen:
                        raise ValueError('Duplicate case across shards')
                    seen.add(row['caseId'])
                    line(streams[name], row)
        snapshots = {}
        for shard in shards:
            for row in rows(shard, 'snapshots'):
                sid = row['snapshotId']
                digest = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
                if sid in snapshots:
                    if snapshots[sid] != digest:
                        raise ValueError('Conflicting snapshot')
                else:
                    snapshots[sid] = digest
                    line(streams['snapshots'], row)
        games, audit, _ = audited
        parts = dataset_partitions(games, first['trainingStart'], first['validationStart'], first['testStart'])
        excluded = {split: Counter() for split in SPLITS}
        for split in SPLITS:
            chosen = set(selected[split])
            for game in parts[split]:
                gid = game['gameId']
                reasons = audit[gid]['reasons'] or ([] if gid in chosen else ['sample_limit'])
                if reasons:
                    excluded[split].update(reasons)
                    line(streams['exclusions'], {'gameId': gid, 'split': split, 'reasons': reasons})
    reports = [read(path / 'report.json') for path in shards]
    report = dict(reports[0])
    for field in ('checks',):
        counts = Counter()
        for item in reports:
            counts.update(item[field])
        report[field] = dict(counts)
    for field in ('evidenceQuality', 'stageCounts', 'abstentions'):
        report[field] = {}
        for split in SPLITS:
            counts = Counter()
            for item in reports:
                counts.update(item[field][split])
            report[field][split] = dict(counts)
    report['metrics'] = {}
    for split in SPLITS:
        report['metrics'][split] = {}
        for variant in compact.VARIANTS:
            metric = compact.StreamingMetrics()
            for item in reports:
                metric.counts.update({key: item['metrics'][split][variant][key] for key in metric.counts})
            report['metrics'][split][variant] = metric.report()
    report['selectedGames'] = report['exportedGames'] = {s: len(selected[s]) for s in SPLITS}
    report['excluded'] = {s: dict(excluded[s]) for s in SPLITS}
    report['timing'] = {key: sum(r['timing'][key] for r in reports)
                        for key in ('scorerTotalMs', 'featuresAndChecksTotalMs')}
    # Accumulated shard runtime is reproducible when resuming a partial final
    # publication. It is worker time, not wall-clock time for this invocation.
    report['timing']['elapsedSeconds'] = sum(r['timing']['elapsedSeconds'] for r in reports)
    report['timing']['elapsedPolicy'] = 'sum_of_completed_shard_elapsed_seconds'
    write_json(output / 'report.json', report)
    manifest = {**first, 'selectedGames': report['selectedGames'],
                'maxTrainingGames': None, 'maxValidationGames': None,
                'artifacts': {name: compact.file_hash(output / name) for name in sorted(ARTIFACTS)}}
    write_json(output / 'manifest.json', manifest)
    return report


def build(prepared, raw_dir, output, workers=2, chunk_games=50, max_validation=None):
    if workers not in (1, 2, 3) or type(chunk_games) is not int or chunk_games < 1:
        raise ValueError('Use 1-3 workers and a positive chunk size')
    if max_validation is not None and (type(max_validation) is not int or max_validation < 1):
        raise ValueError('Validation limit must be positive')
    prepared, raw_dir, output = map(Path, (prepared, raw_dir, output))
    state_path = output / '_shards' / 'state.json'
    code = {**compact.code_hashes(), 'resume_dataset.py': compact.file_hash(Path(__file__))}
    prior = read(state_path) if state_path.exists() else None
    if prior and (prior['code'] != code or any(compact.file_hash(Path(p)) != h for p, h in prior['inputs'].items())):
        raise ValueError('Source or input changed; cannot reuse checkpoints')
    audited = audit_sources(prepared, raw_dir)
    games, audit, provenance = audited
    parts = dataset_partitions(games, '2024-04-01', '2025-01-01', '2026-01-01')
    selected = {}
    for split in SPLITS:
        eligible = [g['gameId'] for g in parts[split] if audit[g['gameId']]['eligible']]
        if not eligible:
            raise ValueError('No supported opening games in ' + split)
        keep = sample_indices(len(eligible), max_validation if split == 'validation' else None)
        selected[split] = [gid for i, gid in enumerate(eligible) if i in keep]
    state = {'code': code, 'inputs': current_inputs(prepared, raw_dir, provenance),
             'selected': selected, 'chunkGames': chunk_games, 'maxValidationGames': max_validation}
    if prior and prior != state:
        raise ValueError('Resume configuration mismatch')
    if not prior:
        if output.exists():
            raise FileExistsError('Existing directory has no resume state: ' + str(output))
        state_path.parent.mkdir(parents=True)
        write_json(state_path, state)
    if (output / 'manifest.json').exists():
        verify(output)
        return read(output / 'report.json')
    jobs = [{s: selected[s][i:i + chunk_games] for s in SPLITS}
            for i in range(0, max(map(len, selected.values())), chunk_games)]
    completed = {}
    for index, job in enumerate(jobs):
        for candidate in sorted(state_path.parent.glob(f'{index:06d}-*')):
            if not (candidate / 'manifest.json').exists():
                continue
            manifest = verify(candidate)
            actual = {s: set() for s in SPLITS}
            for context in rows(candidate, 'contexts'):
                actual[context['split']].add(context['gameId'])
            if actual != {s: set(job[s]) for s in SPLITS} or manifest['input'] != provenance or manifest['codeSha256'] != compact.code_hashes():
                raise ValueError('Shard selection/source mismatch')
            completed[index] = candidate
            break
    print(f'Resuming {len(completed)}/{len(jobs)} completed shards', flush=True)
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn'),
                             initializer=initialize, initargs=(audited,)) as pool:
        futures = {pool.submit(export_shard, prepared, raw_dir,
                               state_path.parent / f'{i:06d}-{uuid4().hex}', job): i
                   for i, job in enumerate(jobs) if i not in completed}
        for future in as_completed(futures):
            completed[futures[future]] = future.result()
            print(f'Checkpoint complete: {len(completed)}/{len(jobs)} shards', flush=True)
    staging = state_path.parent / ('merge-' + uuid4().hex)
    report = merge([completed[i] for i in range(len(jobs))], staging, selected, audited)
    manifest = read(staging / 'manifest.json')
    manifest['maxValidationGames'] = max_validation
    manifest['codeSha256']['resume_dataset.py'] = code['resume_dataset.py']
    write_json(staging / 'manifest.json', manifest)
    if current_inputs(prepared, raw_dir, provenance) != state['inputs'] or {
            **compact.code_hashes(), 'resume_dataset.py': compact.file_hash(Path(__file__))} != code:
        raise ValueError('Source or input changed during export')
    # Recover partial publication by preserving any previously moved final file.
    for name in [*sorted(ARTIFACTS), 'manifest.json']:
        target = output / name
        if target.exists():
            if compact.file_hash(target) != compact.file_hash(staging / name):
                raise ValueError('Partial publication differs: ' + name)
        else:
            (staging / name).rename(target)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'raw-dir', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--chunk-games', type=int, default=50)
    parser.add_argument('--max-validation-games', type=int)
    args = parser.parse_args()
    build(args.prepared, args.raw_dir, args.output, args.workers, args.chunk_games, args.max_validation_games)


if __name__ == '__main__':
    main()
