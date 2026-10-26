// WebSocket messages (spec 9.4), as backend/app/session.py sends them today.
// Every server message carries type, t (match seconds) and wall (server time in ms).

export type TeamId = string;
export type PlayerId = string;

export interface Player {
  id: PlayerId;
  full_name: string;
  surname: string;
  shirt_number: number;
  position: string;
}

export interface Team {
  id: TeamId;
  name: string;
  short_name: string;
  players: Player[];
  lineup: PlayerId[];
}

export interface MatchMeta {
  match_id: string;
  home_team_id: TeamId;
  away_team_id: TeamId;
  teams: Team[];
}

export interface MatchEvent {
  event_id: string;
  seq: number;
  t: number;
  period: number;
  clock: string;
  type: string;
  team_id: TeamId | null;
  player_id: PlayerId | null;
  x: number;
  y: number;
  possession_id: number;
  under_pressure: boolean;
  tags: string[];
  [extra: string]: unknown;
}

export interface ClubStats {
  possession: number;
  shots: number;
  shots_on_target: number;
  passes: number;
  passes_completed: number;
  pass_accuracy: number | null;
  corners: number;
  fouls: number;
  yellow_cards: number;
  red_cards: number;
  offsides: number;
  tackles_won: number;
  interceptions: number;
  duels_won: number;
  xg: number;
}

export interface PlayerStats {
  team_id: TeamId | null;
  touches: number;
  passes: number;
  passes_completed: number;
  shots: number;
  xg: number;
  tackles: number;
  duels_won: number;
  distance_km: number;
  top_speed_kmh: number;
  sprints: number;
}

export interface PressureStats {
  ppda: number | null;
  pressing_height_m: number | null;
  field_tilt: number | null;
  high_regains: number;
  high_regains_5min: number;
}

export interface Patterns {
  chaos: { value: number | null; in_control: TeamId | null };
  pressure: Record<TeamId, PressureStats>;
  rhythm: {
    events_per_min: number | null;
    passes_per_min: number | null;
    since_stoppage_s: number;
    in_play_share: number | null;
    tempo: "Slow" | "Steady" | "Frantic" | null;
  };
  momentum: { value: number; threat: Record<TeamId, number> };
}

interface Envelope {
  t: number;
  wall: number;
}

export interface SessionReadyMessage extends Envelope {
  type: "session.ready";
  session_id: string;
  match: MatchMeta;
  profile: Record<string, unknown>;
  card: unknown;
  speed: Speed;
  paused: boolean;
  duration: number;
}

export interface FrameMessage extends Envelope {
  type: "frame";
  ball: [number, number, number];
  players: [PlayerId, number, number][];
}

export interface EventMessage extends Envelope {
  type: "event";
  event: MatchEvent;
  significance: number;
}

export interface StatsMessage extends Envelope {
  type: "stats";
  score: Record<TeamId, number>;
  ball_in_play_s: number;
  clubs: Record<TeamId, ClubStats>;
  players: Record<PlayerId, PlayerStats>;
  patterns: Patterns;
}

export type ServerMessage = SessionReadyMessage | FrameMessage | EventMessage | StatsMessage;

export const SPEEDS = [1, 5, 10] as const;
export type Speed = (typeof SPEEDS)[number];

export type ClientMessage =
  | { type: "replay.speed"; speed: Speed }
  | { type: "dev.pause"; on: boolean }
  | { type: "dev.jump"; t: number };
