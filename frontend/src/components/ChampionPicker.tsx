import { useState } from 'react';
import type { CatalogChampion } from '../api/champions';
interface Props {
  champions: CatalogChampion[];
  unavailable?: string[];
  selected?: string | null;
  onSelect: (id: string) => void;
  disabled?: boolean;
}
export default function ChampionPicker({ champions, unavailable = [], selected, onSelect, disabled = false }: Props) {
  const [search, setSearch] = useState('');
  const normalize = (text: string) => text.toLowerCase().replace(/[^a-z0-9]/g, '');
  const matches = champions.filter(c => normalize(c.name).includes(normalize(search)));
  return <div className="champion-picker">
    <label className="champion-search">Search champions
      <input type="search" value={search} placeholder="Search by name…" onChange={e => setSearch(e.target.value)} />
    </label>
    <div className="champion-grid" aria-label="Champion catalog">
      {matches.map(c => <button type="button" key={c.id} aria-label={c.name} aria-pressed={selected === c.id}
        className={'champion-tile' + (selected === c.id ? ' active' : '')}
        disabled={disabled || unavailable.includes(c.id)} onClick={() => onSelect(c.id)}>
        <img src={c.portrait} alt="" loading="lazy" width="64" height="64" />
        <span>{c.name}</span>
      </button>)}
    </div>
    {!matches.length && <p className="muted">No champions match your search.</p>}
  </div>;
}
