import { request } from './teams';
import type { Team, Role } from './teams';
import type { Action, Format, Side } from '../draft/rules';
export interface GameRequest {
  requestId: string; format: Format; side: Side; result: 'WIN' | 'LOSS'; patch: string; actions: Action[];
}
export interface Game extends Omit<GameRequest, 'requestId'> {
  id: number; teamId: number; roster: Team; championNames: Record<string, string>; recordedAt: string;
  assignments: Assignment[]; assignmentVersion: number;
}
export interface Assignment { side: Side; championId: string; role: Role }
export const saveAssignments = (game: Game, assignments: Assignment[]) => request<Game>(`/api/teams/${game.teamId}/games/${game.id}/assignments`, {
  method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ version: game.assignmentVersion, assignments }),
});
export const listGames = (teamId: number) => request<Game[]>(`/api/teams/${teamId}/games`);
export const recordGame = (teamId: number, game: GameRequest) => request<Game>(`/api/teams/${teamId}/games`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(game),
});
