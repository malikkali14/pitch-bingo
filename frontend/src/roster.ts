import type { MatchMeta, Player, PlayerId, Team, TeamId } from "./protocol";

export interface RosterEntry extends Player {
  team: Team;
  home: boolean;
}

export interface Roster {
  home: Team;
  away: Team;
  players: Map<PlayerId, RosterEntry>;
  team(id: TeamId | null | undefined): Team | undefined;
}

export function buildRoster(meta: MatchMeta): Roster {
  const home = meta.teams.find((t) => t.id === meta.home_team_id) ?? meta.teams[0];
  const away = meta.teams.find((t) => t.id === meta.away_team_id) ?? meta.teams[1];
  const players = new Map<PlayerId, RosterEntry>();
  for (const team of [home, away]) {
    for (const p of team.players) players.set(p.id, { ...p, team, home: team === home });
  }
  return {
    home,
    away,
    players,
    team: (id) => (id === home.id ? home : id === away.id ? away : undefined),
  };
}

/** The home club attacks x = 105 in the first half and x = 0 in the second (spec 3). */
export function attacksRight(teamId: string | null, period: number, homeId: string): boolean {
  return (teamId === homeId) === (period === 1);
}
