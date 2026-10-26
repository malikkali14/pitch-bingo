// Match state built from server messages. Frames are kept out of here (see frames.ts) so the
// whole screen doesn't re-render ten times a second.

import { type ClockAnchor } from "../clock";
import { feedEntry, type FeedEntry } from "../feed/templates";
import type { MatchEvent, MatchMeta, ServerMessage, Speed, StatsMessage } from "../protocol";
import { buildRoster, type Roster } from "../roster";
import { initialBall, nextBall, type BallState } from "./ball";

export const FEED_LIMIT = 100;
export const CUE_LIMIT = 40;

export type Status = "connecting" | "live" | "error";

export interface Cue {
  event: MatchEvent;
  at: number; // performance.now() when it arrived
}

export interface XgPoint {
  t: number;
  home: number;
  away: number;
}

export interface MatchState {
  status: Status;
  sessionId: string | null;
  meta: MatchMeta | null;
  roster: Roster | null;
  speed: Speed;
  anchor: ClockAnchor | null;
  fullTime: boolean;
  feed: FeedEntry[];
  cues: Cue[];
  cards: Record<string, "yellow" | "red">;
  ball: BallState;
  stats: StatsMessage | null;
  xg: XgPoint[];
}

export const initialState: MatchState = {
  status: "connecting",
  sessionId: null,
  meta: null,
  roster: null,
  speed: 1,
  anchor: null,
  fullTime: false,
  feed: [],
  cues: [],
  cards: {},
  ball: initialBall,
  stats: null,
  xg: [],
};

export type Action =
  | { kind: "message"; msg: ServerMessage; now: number }
  | { kind: "status"; status: Status }
  | { kind: "speed"; speed: Speed };

export function matchReducer(state: MatchState, action: Action): MatchState {
  switch (action.kind) {
    case "status":
      return { ...state, status: action.status };
    case "speed":
      return { ...state, speed: action.speed };
    case "message":
      return onMessage(state, action.msg, action.now);
  }
}

function onMessage(state: MatchState, msg: ServerMessage, now: number): MatchState {
  switch (msg.type) {
    case "session.ready":
      return {
        ...initialState,
        status: "live",
        sessionId: msg.session_id,
        meta: msg.match,
        roster: buildRoster(msg.match),
        speed: msg.speed,
      };
    case "event":
      return onEvent(state, msg.event, now);
    case "stats":
      return onStats(state, msg);
    case "frame":
      return state;
  }
}

function onEvent(state: MatchState, e: MatchEvent, now: number): MatchState {
  const next = {
    ...state,
    anchor: { t: e.t, clock: e.clock, period: e.period },
    // A dev jump back in time un-ends the match.
    fullTime:
      (e.type === "period_end" && e.period === 2) ||
      (state.fullTime && e.t >= (state.anchor?.t ?? 0)),
    cues: [...state.cues.slice(-(CUE_LIMIT - 1)), { event: e, at: now }],
    ball: state.roster ? nextBall(state.ball, e, state.roster) : state.ball,
  };
  if (e.type === "card" && e.player_id) {
    next.cards = { ...state.cards, [e.player_id]: e.card === "yellow" ? "yellow" : "red" };
  }
  const entry = state.roster ? feedEntry(e, state.roster) : null;
  if (entry && !state.feed.some((f) => f.entry_id === entry.entry_id)) {
    next.feed = [entry, ...state.feed].slice(0, FEED_LIMIT);
  }
  return next;
}

function onStats(state: MatchState, msg: StatsMessage): MatchState {
  const meta = state.meta;
  if (!meta) return { ...state, stats: msg };
  const point = {
    t: msg.t,
    home: msg.clubs[meta.home_team_id]?.xg ?? 0,
    away: msg.clubs[meta.away_team_id]?.xg ?? 0,
  };
  // A jump back in time (dev panel) restarts the timeline from that point.
  const kept = state.xg.filter((p) => p.t < msg.t);
  const last = kept[kept.length - 1];
  const xg = last && last.home === point.home && last.away === point.away ? kept : [...kept, point];
  return { ...state, stats: msg, xg };
}
