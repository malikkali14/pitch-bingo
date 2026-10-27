// WebSocket messages (spec 9.4), as backend/app/session.py sends them.
// Every server message carries type, t (match seconds) and wall (server time in ms).

import type { Board, Cell, Square } from "./card/types";

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

// A stat an open square depends on comes as null while it's masked (spec 4.9).
export interface ClubStats {
  possession: number | null;
  shots: number | null;
  shots_on_target: number | null;
  passes: number;
  passes_completed: number;
  pass_accuracy: number | null;
  corners: number | null;
  fouls: number | null;
  yellow_cards: number | null;
  red_cards: number | null;
  offsides: number | null;
  tackles_won: number;
  interceptions: number;
  duels_won: number;
  xg: number | null;
}

export interface PlayerStats {
  team_id: TeamId | null;
  touches: number;
  passes: number;
  passes_completed: number;
  shots: number | null;
  xg: number | null;
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

export type Mode = "normal" | "advanced";
export type StrategistSetting = "auto" | "suggest" | "manual";

export interface Profile {
  mode: Mode;
  club: TeamId | "neutral";
  focus_player_id: PlayerId | null;
  language: string;
  strategist: StrategistSetting;
  handle: string;
}

export interface SessionReadyMessage extends Envelope {
  type: "session.ready";
  session_id: string;
  match: MatchMeta;
  profile: Profile;
  card: Board;
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
  held: boolean; // its feed line waits until a window closes (feed.reveal)
}

export interface StatsMessage extends Envelope {
  type: "stats";
  score: Record<TeamId, number>;
  ball_in_play_s: number;
  clubs: Record<TeamId, ClubStats>;
  players: Record<PlayerId, PlayerStats>;
  patterns: Patterns;
  masked: string[];
}

export interface MaskMessage extends Envelope {
  type: "mask.on" | "mask.off";
  square_id: string;
  tags: string[];
}

export interface WindowOpenMessage extends Envelope {
  type: "square.window_open";
  square_id: string;
  closes_at: number; // wall-clock ms
}

export interface SquareAddedMessage extends Envelope {
  type: "square.added";
  square: Square;
}

export type ResultStatus = "correct" | "wrong" | "too_early" | "missed" | "void";

export interface SquareResultMessage extends Envelope {
  type: "square.result";
  square_id: string;
  status: ResultStatus;
  points: number;
  correct_answer: string | null;
}

export interface SquareExplanationMessage extends Envelope {
  type: "square.explanation";
  square_id: string;
  text: string;
  ai?: boolean; // the rules tutor's or narrator's version, replacing the template one
}

export interface RecapContent {
  headline: string;
  paragraphs: string[];
  talking_points: string[];
  club_paragraph: string | null;
  player_paragraph: string | null;
  bingo_summary: string | null;
}

/** Half-time and full-time recaps (spec 8.6, 9.4): a template first, the AI version after. */
export interface RecapMessage extends Envelope {
  type: "recap";
  kind: "halftime" | "full_time" | "catch_up" | "bingo";
  content: RecapContent;
  ai: boolean;
}

export interface BoardUpdateMessage extends Envelope, Board {
  type: "board.update";
}

export interface BoardLineMessage extends Envelope {
  type: "board.line";
  line: string;
  points: number;
  blank_slate: boolean;
}

export interface FullCardMessage extends Envelope {
  type: "board.full_card";
  points: number;
}

export interface StrategyMove {
  from_cell: Cell;
  to_cell: Cell;
}

export interface StrategyAdviceMessage extends Envelope {
  type: "strategy.advice";
  advice_id: string;
  moves: StrategyMove[];
  before: number;
  after: number;
  reason: string;
  applied: boolean;
}

export interface LeaderboardRow {
  rank: number;
  handle: string;
  points: number;
  correct: number;
  avg_answer_s: number | null;
  you: boolean;
}

export interface LeaderboardMessage extends Envelope {
  type: "leaderboard";
  mode: Mode;
  rows: LeaderboardRow[];
  total: number; // everyone ranked: you plus the simulated fans
}

/** An AI line for a moment (spec 9.4 feed.replace): it replaces the template line with the
 * same entry_id, or adds a line where the moment had none. */
export interface FeedReplaceMessage extends Envelope {
  type: "feed.replace";
  entry_id: string;
  text: string;
  ai: true;
  clock: string;
  event_type: string;
  held: boolean;
}

export interface FeedRevealMessage extends Envelope {
  type: "feed.reveal";
  entry_ids: string[];
}

export interface AgentHealth {
  calls: number;
  ai: number;
  fallbacks: number;
  timeouts: number;
  errors: number;
  verifier_failures: number;
  per_minute: number;
  latency_ms: number | null;
  breaker: "closed" | "open" | "half_open" | "forced";
  trips: number;
  skipped: number;
}

/** Agent status for the dev panel (spec 3, 9.4). */
export interface HealthMessage extends Envelope {
  type: "health";
  online: boolean;
  agents: Record<string, AgentHealth>;
  llm_calls_per_minute: number;
  events_per_minute: number;
}

export interface ErrorMessage extends Envelope {
  type: "error";
  request: string;
  reason: string;
}

export type ServerMessage =
  | SessionReadyMessage
  | FrameMessage
  | EventMessage
  | StatsMessage
  | MaskMessage
  | WindowOpenMessage
  | SquareAddedMessage
  | SquareResultMessage
  | SquareExplanationMessage
  | BoardUpdateMessage
  | BoardLineMessage
  | FullCardMessage
  | StrategyAdviceMessage
  | LeaderboardMessage
  | FeedRevealMessage
  | FeedReplaceMessage
  | HealthMessage
  | RecapMessage
  | ErrorMessage;

export const SPEEDS = [1, 5, 10] as const;
export type Speed = (typeof SPEEDS)[number];

export type ClientMessage =
  | { type: "replay.speed"; speed: Speed }
  | { type: "answer.submit"; square_id: string; value: string }
  | { type: "board.move"; from_cell: Cell; to_cell: Cell }
  | { type: "strategy.apply"; advice_id: string }
  | { type: "profile.set"; strategist?: StrategistSetting; handle?: string; language?: string }
  | { type: "dev.pause"; on: boolean }
  | { type: "dev.jump"; t?: number; minute?: number }
  | { type: "dev.narrator_down"; on: boolean };
