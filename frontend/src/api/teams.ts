export const roles = ["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"] as const;
export type Role = (typeof roles)[number];
export interface Champion {
  name: string;
  comfort: number;
}
export interface Player {
  role: Role;
  name: string;
  riotId: string;
  champions: Champion[];
}
export interface Team {
  id: number;
  name: string;
  version: number;
  players: Player[];
}

// Keep transport errors here so components only need to display a useful message.
export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error(
      "Unable to connect to Beatrice. Start the backend and retry.",
    );
  }
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new Error(
      problem.detail || "The request could not be completed. Please retry.",
    );
  }
  return response.json() as Promise<T>;
}
export const listTeams = () => request<Team[]>("/api/teams");
export const createTeam = (name: string) =>
  request<Team>("/api/teams", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
export const saveTeam = (team: Team) =>
  request<Team>("/api/teams/" + team.id, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(team),
  });
