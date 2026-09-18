import type { Action, Format, Side } from '../draft/rules';
export interface PickRecommendation {
  championId: string; javaScore: number; mlBonus: number; score: number;
  mlEvidenceQuality: string; feasibleRoles?: string[];
}
export interface PickReply { requestId: string; modelVersion: string; picks: PickRecommendation[] }
export interface PickContext { format: Format; side: Side; patch: string; actions: Action[] }
export async function fetchPicks(teamId: number, context: PickContext, signal: AbortSignal): Promise<PickReply> {
  const response = await fetch(`/api/teams/${teamId}/draft/picks`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(context), signal,
  });
  if (!response.ok) throw new Error('Pick suggestions unavailable. You can continue drafting.');
  return response.json();
}
export async function recordPickSelection(teamId: number, requestId: string, championId: string) {
  // Monitoring is best effort and must never delay or reject a user's draft action.
  try {
    await fetch(`/api/teams/${teamId}/draft/picks/selected`, { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ requestId, championId }) });
  } catch { /* Drafting continues even if monitoring is unavailable. */ }
}
