"""Capture local read-only inputs for the reproducible offline scenario suite."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'data/oracle/saved-team-readiness/snapshot.json'


def get(path):
    with urllib.request.urlopen('http://localhost:8080' + path, timeout=15) as response:
        return json.load(response)


if __name__ == '__main__':
    if OUTPUT.exists():
        raise FileExistsError('Snapshot already exists; keep the fixed scenario inputs')
    teams, catalog = get('/api/teams'), get('/api/champions')
    # Database credentials remain inside the container. Only champion metadata is returned.
    sql = "select coalesce(json_agg(t),'[]'::json) from (select champion_id,raw_metadata from reference_champion_metadata where import_id=(select max(import_id) from reference_champion_metadata) order by champion_id) t"
    command = 'PGOPTIONS="-c default_transaction_read_only=on" psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c ' + "'" + sql.replace("'", "'\"'\"'") + "'"
    result = subprocess.run(['docker', 'exec', 'beatrice-postgres-1', 'sh', '-c', command],
                            capture_output=True, text=True, check=True, timeout=30)
    metadata = json.loads(result.stdout)
    if teams != get('/api/teams'):
        raise ValueError('Saved teams changed during capture; retry before running scenarios')
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('x', encoding='utf-8') as stream:
        json.dump({'capturedAt': datetime.now(timezone.utc).isoformat(), 'teams': teams,
                   'catalog': catalog, 'metadata': metadata,
                   'playerHistory': 'No verified mapping to professional player IDs; familiarity counts stay missing.'}, stream, indent=2)
    print(json.dumps({'output': str(OUTPUT), 'teams': len(teams), 'metadataChampions': len(metadata)}))
