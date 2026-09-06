import { useEffect, useState } from 'react';
import type { Catalog } from '../api/champions';
import { championEvidence, referenceOptions } from '../api/reference';
import type { Evidence, ReferenceOptions } from '../api/reference';
import { roles } from '../api/teams';

export default function ReferenceExplorer({ catalog }: { catalog: Catalog }) {
  const [options, setOptions] = useState<ReferenceOptions | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [sliceIndex, setSliceIndex] = useState(0);
  const [championId, setChampionId] = useState(catalog.champions[0]?.id ?? '');
  const [role, setRole] = useState<string>('TOP');
  useEffect(() => {
    let current = true;
    referenceOptions().then(data => { if (current) setOptions(data); }).catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [retry]);
  return <section className="panel reference-explorer">
    <span className="eyebrow">COMPCRAFT ARCHIVE · EXTERNAL EVIDENCE</span>
    <h2>Champion roles & pair observations</h2>
    <p className="muted">Historical network sample, separate from your team's records. These are associations, not causal synergy or a prediction of your win chance. Current catalog: {catalog.version}.</p>
    {error ? <p role="alert">{error} <button onClick={() => { setError(''); setRetry(n => n + 1); }}>Retry reference data</button></p>
      : !options ? <p role="status">Loading reference sources…</p>
      : !options.slices.length ? <p>No reference data imported yet.</p> : <>
        <div className="reference-filters">
          <label>Champion<select value={championId} onChange={e => setChampionId(e.target.value)}>{catalog.champions.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label>Reference role<select value={role} onChange={e => setRole(e.target.value)}>{roles.map(r => <option key={r}>{r}</option>)}</select></label>
          <label>Historical data slice<select value={sliceIndex} onChange={e => setSliceIndex(Number(e.target.value))}>{options.slices.map((s, i) =>
            <option key={i} value={i}>Patch {s.patch} · Queue {s.queueId} · {s.region} · {s.source}</option>)}</select></label>
        </div>
        <EvidenceResult key={`${options.importId}:${sliceIndex}:${championId}:${role}`} championId={championId} role={role} slice={options.slices[sliceIndex]} catalog={catalog} />
      </>}
  </section>;
}

function EvidenceResult({ championId, role, slice, catalog }: { championId: string; role: string; slice: import('../api/reference').Slice; catalog: Catalog }) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    championEvidence(championId, slice, role).then(data => { if (current) setEvidence(data); })
      .catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [championId, role, slice, retry]);
  if (error) return <p role="alert">{error} <button onClick={() => { setError(''); setRetry(n => n + 1); }}>Retry evidence</button></p>;
  if (!evidence) return <p role="status">Loading observations…</p>;
  return <div>
    <p>Possible roles (curated metadata): {evidence.roles.join(', ') || 'Unknown'}. Not a confirmed lane assignment.</p>
    {evidence.roleStats.length ? evidence.roleStats.map((stat, n) => <p key={n}>{role}: {stat.wins} wins / {stat.games} observations · {(stat.winRate * 100).toFixed(1)}% observed win rate.</p>)
      : <p>No role statistic for this exact slice. Missing data does not mean a zero win rate.</p>}
    <p className="muted">Up to 40 pairs, ordered by sample size. Δ compares the pair's observed win rate with the mean of both individual role baselines. Those samples overlap; this is not an independent experiment.</p>
    {!evidence.synergies.length ? <p>No pair observations for this exact slice.</p> : <div className="reference-table-scroll"><table className="reference-table">
      <thead><tr><th>Ally</th><th>Ally role</th><th>Wins / observations</th><th>Observed rate</th><th>Δ baseline</th><th>Sample warning</th></tr></thead>
      <tbody>{evidence.synergies.map((stat, n) => <tr key={n}>
        <td>{catalog.champions.find(c => c.id === stat.partnerId)?.name ?? stat.partnerId}</td><td>{stat.partnerRole}</td>
        <td>{stat.wins} / {stat.games}</td><td>{(stat.winRate * 100).toFixed(1)}%</td>
        <td>{stat.delta === null ? 'Unavailable' : `${stat.delta >= 0 ? '+' : ''}${(stat.delta * 100).toFixed(1)} pp`}</td>
        <td>{stat.games < 20 ? 'Very small sample' : stat.games < 100 ? 'Limited sample' : 'Still observational'}</td>
      </tr>)}</tbody>
    </table></div>}
    <p className="muted">pp = percentage points. The original “confidence” was a sample-size heuristic, not statistical confidence. No hidden merging across patches, queues, or mirrored pairs.</p>
  </div>;
}
