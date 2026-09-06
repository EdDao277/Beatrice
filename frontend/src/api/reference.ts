import { request } from './teams';
export interface Slice { patch: string; queueId: number; region: string; source: string }
export interface ReferenceOptions { importId: number | null; slices: Slice[] }
export interface ReferenceStat { role: string; partnerId: string | null; partnerRole: string | null; games: number; wins: number; winRate: number; delta: number | null; tier: string | null }
export interface Evidence { roles: string[]; roleStats: ReferenceStat[]; synergies: ReferenceStat[] }
export const referenceOptions = () => request<ReferenceOptions>('/api/reference/options');
export const championEvidence = (id: string, slice: Slice, role: string) => request<Evidence>(
  `/api/reference/champions/${encodeURIComponent(id)}?` + new URLSearchParams({ patch: slice.patch,
    queueId: String(slice.queueId), region: slice.region, source: slice.source, role }));
