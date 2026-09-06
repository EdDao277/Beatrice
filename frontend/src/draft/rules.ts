export type Format = 'RANKED' | 'TOURNAMENT';
export type Side = 'BLUE' | 'RED';
export type Kind = 'BAN' | 'PICK';
export interface Action { side: Side; kind: Kind; championId: string | null }
export const formatLabel = (format: Format) => format === 'RANKED' ? 'Ranked / Normal Draft' : 'Tournament';
const rankedPicks: Side[] = ['BLUE','RED','RED','BLUE','BLUE','RED','RED','BLUE','BLUE','RED'];
const tournamentSides: Side[] = ['BLUE','RED','BLUE','RED','BLUE','RED','BLUE','RED','RED','BLUE','BLUE','RED','RED','BLUE','RED','BLUE','RED','BLUE','BLUE','RED'];

// Ranked bans are simultaneous in the client: entry order is deliberately free.
export function nextTurn(format: Format, actions: Action[]): { kind: Kind; side: Side | null } | null {
  const n = actions.length;
  if (n >= 20) return null;
  if (format === 'RANKED') return n < 10 ? { kind: 'BAN', side: null } : { kind: 'PICK', side: rankedPicks[n - 10] };
  return { kind: n < 6 || (n >= 12 && n < 16) ? 'BAN' : 'PICK', side: tournamentSides[n] };
}
export function unavailable(format: Format, actions: Action[], side: Side): string[] {
  const simultaneous = format === 'RANKED' && actions.length < 10;
  return actions.filter(a => !simultaneous || a.side === side).flatMap(a => a.championId ? [a.championId] : []);
}
export function appendAction(format: Format, actions: Action[], side: Side, championId: string | null): Action[] {
  const turn = nextTurn(format, actions);
  if (!turn || (turn.side && turn.side !== side)) throw new Error('It is not that side’s turn.');
  if (turn.kind === 'BAN' && actions.filter(a => a.kind === 'BAN' && a.side === side).length >= 5) throw new Error('That side has entered all five bans.');
  if (!championId && turn.kind === 'PICK') throw new Error('Choose a champion for this pick.');
  if (championId && unavailable(format, actions, side).includes(championId)) throw new Error('This champion is unavailable.');
  return [...actions, { side, kind: turn.kind, championId }];
}
