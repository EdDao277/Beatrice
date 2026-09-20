import type { Action, Format, Side } from '../draft/rules';
export interface BanReply { bans: { championId: string; basis: 'EVIDENCE_BACKED' | 'POOL_COMPOSITION_FALLBACK' }[] }
export async function fetchBans(teamId: number, context: { format: Format; side: Side; patch: string; actions: Action[] }, signal: AbortSignal): Promise<BanReply> {
  const response = await fetch(`/api/teams/${teamId}/draft/bans`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(context), signal,
  });
  if (!response.ok) throw new Error('Ban suggestions unavailable.');
  const reply: BanReply = await response.json();
  if (!reply || !Array.isArray(reply.bans) || reply.bans.some(b => !b || typeof b.championId !== 'string'
    || !['EVIDENCE_BACKED', 'POOL_COMPOSITION_FALLBACK'].includes(b.basis))) throw new Error('Invalid ban response.');
  return reply;
}
