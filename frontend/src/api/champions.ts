import { useEffect, useState } from 'react';
import { request } from './teams';
export interface CatalogChampion { id: string; name: string; portrait: string }
export interface Catalog { version: string; champions: CatalogChampion[] }
export function useChampions() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let current = true;
    request<Catalog>('/api/champions').then(data => { if (current) setCatalog(data); })
      .catch(e => { if (current) setError(e.message); });
    return () => { current = false; };
  }, [retry]);
  return { catalog, error, retry: () => { setError(''); setRetry(n => n + 1); } };
}
