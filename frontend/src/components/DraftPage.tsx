import type { Team } from '../api/teams';
import { useChampions } from '../api/champions';
import DraftBoard from './DraftBoard';
export default function DraftPage(props: { team: Team; onPending: (value: boolean) => void; onBusy: (value: boolean) => void; onRecorded: () => void }) {
  const { catalog, error, retry } = useChampions();
  if (error) return <section className="panel" role="alert">{error} <button onClick={retry}>Retry catalog</button></section>;
  if (!catalog) return <p role="status">Loading champion catalog…</p>;
  return <DraftBoard {...props} catalog={catalog} />;
}
