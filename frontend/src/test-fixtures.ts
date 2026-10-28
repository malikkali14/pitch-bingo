// Shared test data: a cut-down match from seed 2610.
import type { MatchEvent, MatchMeta, Profile } from "./protocol";

export const META: MatchMeta = {
  match_id: "syn-2610",
  home_team_id: "NBA",
  away_team_id: "KVL",
  teams: [
    { id: "NBA", name: "Northbridge Athletic", short_name: "Northbridge", lineup: ["NBA-01", "NBA-09"],
      players: [
        { id: "NBA-01", full_name: "Nevin Brancati", surname: "Brancati", shirt_number: 1, position: "GK" },
        { id: "NBA-09", full_name: "Tomas Arvel", surname: "Arvel", shirt_number: 9, position: "ST" },
        { id: "NBA-15", full_name: "Ben Ludo", surname: "Ludo", shirt_number: 15, position: "CM" },
      ] },
    { id: "KVL", name: "Kestrel Vale", short_name: "Kestrel", lineup: ["KVL-04"],
      players: [
        { id: "KVL-04", full_name: "Ira Moss", surname: "Moss", shirt_number: 4, position: "CB" },
      ] },
  ],
};

let seq = 0;
export function ev(type: string, fields: Partial<MatchEvent> & Record<string, unknown> = {}): MatchEvent {
  seq += 1;
  return {
    event_id: `e${String(seq).padStart(6, "0")}`, seq, t: 10, period: 1, clock: "00:10", type,
    team_id: "NBA", player_id: "NBA-09", x: 50, y: 34, possession_id: 0, under_pressure: false,
    tags: [], ...fields,
  };
}

export const PROFILE: Profile = {
  mode: "normal", club: "neutral", focus_player_id: null, language: "en", strategist: "suggest",
  handle: "You", units: "metric", my_metric: "none",
};
