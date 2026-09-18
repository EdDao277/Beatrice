"""Read-only real-team HTTP smoke/latency checks; never saves teams or games."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter
from urllib.request import Request, urlopen


def call(base, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def lineup(pools, used=()):
    if not pools:
        return list(used)
    for champion in pools[0]:
        if champion not in used:
            result = lineup(pools[1:], (*used, champion))
            if result:
                return result
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8081)
    parser.add_argument('--label', choices=('online', 'offline'), required=True)
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[2] / f'data/guarded-integration/{args.label}.json'
    if output.exists():
        raise FileExistsError('Preserve the existing verification report')
    base = f'http://127.0.0.1:{args.port}'
    before = call(base, '/api/teams')
    catalog = call(base, '/api/champions')
    names = {c['name'].casefold(): c['id'] for c in catalog['champions']}
    reports = []
    for team in before:
        pools = [sorted({names[c['name'].casefold()] for c in p['champions']
                         if c['name'].casefold() in names}) for p in team['players']]
        own = lineup(pools)
        if not own:
            continue
        enemy = sorted(set(names.values()) - set(own))[:3]
        bans = [{'kind': 'BAN', 'side': side, 'championId': None}
                for side in ('BLUE', 'RED', 'BLUE', 'RED', 'BLUE', 'RED')]
        picks = [{'kind': 'PICK', 'side': side, 'championId': champion} for side, champion in
                 [('BLUE', own[0]), ('RED', enemy[0]), ('RED', enemy[1]),
                  ('BLUE', own[1]), ('BLUE', own[2]), ('RED', enemy[2])]]
        cases = [('blind_blue', 'BLUE', []), ('blind_red', 'RED', []),
                 ('early', 'BLUE', bans + picks[:1]), ('late', 'BLUE', bans + picks)]
        for name, side, actions in cases:
            body = {'format': 'TOURNAMENT', 'side': side, 'patch': catalog['version'], 'actions': actions}
            times, gates, signatures = [], Counter(), []
            first_ms = None
            for iteration in range(21):
                start = perf_counter()
                reply = call(base, f"/api/teams/{team['id']}/draft/picks", body)
                elapsed = (perf_counter() - start) * 1000
                if iteration == 0:
                    first_ms = elapsed
                else:
                    times.append(elapsed)
                selected = reply['picks']
                assert selected, 'Expected legal saved-pool picks in this fixture'
                unavailable = {a['championId'] for a in actions if a['championId']}
                for row in selected:
                    assert row['championId'] not in unavailable
                    assert row['championId'] in set().union(*map(set, pools))
                    assert 0 <= row['mlBonus'] <= 2.5
                    assert row['score'] == row['javaScore'] + row['mlBonus']
                    assert not any(k in row for k in ('probability', 'winChance', 'confidence'))
                    if args.label == 'offline':
                        assert row['mlBonus'] == 0 and row['score'] == row['javaScore']
                gates.update(row['mlEvidenceQuality'] for row in selected)
                signatures.append([{k: row[k] for k in ('championId', 'javaScore', 'mlBonus', 'score', 'components', 'feasibleRoles')}
                                   for row in selected])
            assert all(s == signatures[0] for s in signatures)
            times.sort()
            reports.append({'teamId': team['id'], 'case': name, 'requests': 21,
                            'firstMs': first_ms, 'warmMedianMs': (times[9] + times[10]) / 2,
                            'warmP95Ms': times[18] * .95 + times[19] * .05,
                            'warmMaxMs': times[-1], 'evidenceQuality': dict(gates),
                            'picks': signatures[0]})
    assert reports, 'No complete real saved-pool roster available'
    assert before == call(base, '/api/teams'), 'Saved teams changed during smoke test'
    result = {'at': datetime.now(timezone.utc).isoformat(), 'label': args.label,
              'teamsSha256': digest(before), 'savedTeamsUnchanged': True, 'cases': reports}
    if args.label == 'offline':
        prior = json.loads((output.parent / 'online.json').read_text())
        assert prior['teamsSha256'] == result['teamsSha256']
        for online, offline in zip(prior['cases'], reports, strict=True):
            # Current history is stale: online gating and service-down must agree exactly.
            assert online['case'] == offline['case'] and online['picks'] == offline['picks']
        result['exactMatchToStaleOnlineJavaFallback'] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({**result, 'cases': [{k: v for k, v in row.items() if k != 'picks'} for row in reports]}, indent=2))


if __name__ == '__main__':
    main()
