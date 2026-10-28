// Match state built from server messages. Frames are kept out of here (see frames.ts) so the
// whole screen doesn't re-render ten times a second.

import type { Board, Square } from "../card/types";
import { minuteLabel, type ClockAnchor } from "../clock";
import { feedEntry, iconFor, type FeedEntry } from "../feed/templates";
import { has, t } from "../i18n";
import type {
  EventMessage,
  FeedReplaceMessage,
  HealthMessage,
  LeaderboardRow,
  RecapMessage,
  MatchEvent,
  MatchMeta,
  Profile,
  ServerMessage,
  Speed,
  StatsMessage,
  StrategyAdviceMessage,
} from "../protocol";
import { buildRoster, type Roster } from "../roster";
import { initialBall, nextBall, type BallState } from "./ball";

export const FEED_LIMIT = 100;
export const CUE_LIMIT = 40;
export const MOMENTS = 3;

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

export interface Notice {
  text: string;
  kind: "info" | "error";
  at: number;
}

export interface Moment {
  event: MatchEvent;
  significance: number;
  text: string;
}

export interface MatchState {
  status: Status;
  sessionId: string | null;
  meta: MatchMeta | null;
  roster: Roster | null;
  profile: Profile | null;
  speed: Speed;
  anchor: ClockAnchor | null;
  fullTime: boolean;
  feed: FeedEntry[];
  held: Record<string, FeedEntry>; // feed lines waiting for a window to close (spec 4.9)
  cues: Cue[];
  cards: Record<string, "yellow" | "red">;
  ball: BallState;
  stats: StatsMessage | null;
  xg: XgPoint[];
  board: Board | null;
  masks: Record<string, string[]>; // square id -> tags it hides
  answers: Record<string, string | null>; // square id -> correct answer, once a result shows
  pending: Record<string, string>; // answers sent, waiting for their result
  advice: StrategyAdviceMessage | null; // a suggestion waiting for Apply
  strategistNote: string | null; // the reason for the last automatic move
  leaderboard: LeaderboardRow[];
  ranked: number;
  notice: Notice | null;
  announcement: string; // read out by screen readers when an announced window opens
  moments: Moment[];
  health: HealthMessage | null;
  recaps: Partial<Record<RecapMessage["kind"], RecapMessage>>;
  definition: { term: string; text: string; ai: boolean } | null;
  paused: boolean;
  narratorDown: boolean;
}

export const initialState: MatchState = {
  status: "connecting",
  sessionId: null,
  meta: null,
  roster: null,
  profile: null,
  speed: 1,
  anchor: null,
  fullTime: false,
  feed: [],
  held: {},
  cues: [],
  cards: {},
  ball: initialBall,
  stats: null,
  xg: [],
  board: null,
  masks: {},
  answers: {},
  pending: {},
  advice: null,
  strategistNote: null,
  leaderboard: [],
  ranked: 0,
  notice: null,
  announcement: "",
  moments: [],
  health: null,
  recaps: {},
  definition: null,
  paused: false,
  narratorDown: false,
};

export type Action =
  | { kind: "message"; msg: ServerMessage; now: number }
  | { kind: "status"; status: Status }
  | { kind: "speed"; speed: Speed }
  | { kind: "answer"; squareId: string; value: string }
  | { kind: "moved" }
  | { kind: "dev"; paused?: boolean; narratorDown?: boolean }
  | { kind: "define"; term: string | null };

export function matchReducer(state: MatchState, action: Action): MatchState {
  switch (action.kind) {
    case "status":
      return { ...state, status: action.status };
    case "speed":
      return { ...state, speed: action.speed };
    case "answer":
      return { ...state, pending: { ...state.pending, [action.squareId]: action.value } };
    case "moved":
      return { ...state, advice: null };
    case "define":
      return { ...state, definition: action.term === null ? null
        : { term: action.term, text: "", ai: false } };
    case "dev":
      return { ...state, paused: action.paused ?? state.paused,
        narratorDown: action.narratorDown ?? state.narratorDown };
    case "message":
      return onMessage(state, action.msg, action.now);
  }
}

/** Tags hidden right now: any open square's masks (spec 4.9). */
export function maskedTags(state: Pick<MatchState, "masks">): Set<string> {
  return new Set(Object.values(state.masks).flat());
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
        profile: msg.profile,
        speed: msg.speed,
        board: msg.card,
        paused: msg.paused,
      };
    case "event":
      return onEvent(state, msg, now);
    case "stats":
      return onStats(state, msg);
    case "frame":
      return state;
    case "mask.on":
      return { ...state, masks: { ...state.masks, [msg.square_id]: msg.tags } };
    case "mask.off": {
      const masks = { ...state.masks };
      delete masks[msg.square_id];
      return { ...state, masks };
    }
    case "feed.reveal":
      return reveal(state, msg.entry_ids);
    case "feed.replace":
      return replaceLine(state, msg);
    case "square.window_open": {
      const square = state.board?.squares.find((s) => s.id === msg.square_id);
      const next = updateSquare(state, msg.square_id, { state: "open", closes_at: msg.closes_at });
      if (!square) return next;
      const text = square.text[state.profile?.language ?? "en"] ?? square.text.en ?? "";
      return { ...next, announcement: t("card.announce", { question: text }) };
    }
    case "square.added": {
      const next = replaceSquare(state, msg.square);
      const text = msg.square.text[state.profile?.language ?? "en"] ?? msg.square.text.en ?? "";
      return { ...next, announcement: t("card.announce_live", { question: text }) };
    }
    case "square.result": {
      const pending = { ...state.pending };
      delete pending[msg.square_id];
      const square = state.board?.squares.find((s) => s.id === msg.square_id);
      const live = square?.kind === "live";
      const next = updateSquare(state, msg.square_id, {
        state: msg.status === "correct" && live ? "wildcard" : msg.status,
        result: {
          status: msg.status,
          points: msg.points,
          explanation: square?.result?.explanation ?? "",
          evidence_event_ids: square?.result?.evidence_event_ids ?? [],
        },
      });
      return { ...next, pending, answers: { ...state.answers, [msg.square_id]: msg.correct_answer } };
    }
    case "square.explanation":
      return explain(state, msg.square_id, msg.text, !!msg.ai);
    case "recap":
      return onRecap(state, msg);
    case "definition":
      // Only the term the viewer asked about; never let a stored line replace the tutor's.
      if (state.definition?.term !== msg.term || (state.definition.ai && !msg.ai)) return state;
      return { ...state, definition: { term: msg.term, text: msg.text, ai: msg.ai } };
    case "board.update": {
      const { squares, scored_lines, points, correct, bingos, full_card } = msg;
      return { ...state, board: { squares, scored_lines, points, correct, bingos, full_card } };
    }
    case "board.line":
      return notice(state, t(msg.blank_slate ? "card.blank_slate" : "card.line_scored",
        { points: msg.points }), "info", now);
    case "board.full_card":
      return notice(state, t("card.full_card", { points: msg.points }), "info", now);
    case "strategy.advice":
      return msg.applied
        ? { ...state, advice: null, strategistNote: msg.reason }
        : { ...state, advice: msg, strategistNote: null };
    case "health":
      return { ...state, health: msg, narratorDown: msg.agents.narrator?.breaker === "forced" };
    case "leaderboard":
      return { ...state, leaderboard: msg.rows, ranked: msg.total };
    case "error": {
      // A refused answer frees the square to try again; anything else just shows.
      const pending = msg.request === "answer.submit" ? {} : state.pending;
      return { ...notice(state, msg.reason, "error", now), pending };
    }
  }
}

function notice(state: MatchState, text: string, kind: Notice["kind"], at: number): MatchState {
  return { ...state, notice: { text, kind, at } };
}

function updateSquare(state: MatchState, id: string, patch: Partial<Square>): MatchState {
  if (!state.board) return state;
  const squares = state.board.squares.map((s) => (s.id === id ? { ...s, ...patch } : s));
  return { ...state, board: { ...state.board, squares } };
}

function replaceSquare(state: MatchState, square: Square): MatchState {
  if (!state.board) return state;
  const squares = state.board.squares.map((s) => (s.id === square.id ? square : s));
  return { ...state, board: { ...state.board, squares } };
}

function onEvent(state: MatchState, msg: EventMessage, now: number): MatchState {
  const e = msg.event;
  const next = {
    ...state,
    anchor: { t: e.t, clock: e.clock, period: e.period },
    // A dev jump back in time un-ends the match.
    fullTime:
      (e.type === "period_end" && e.period === 2) ||
      (state.fullTime && e.t >= (state.anchor?.t ?? 0)),
    // A held event's cue would give away the answer, so it never shows on the pitch.
    cues: msg.held ? state.cues : [...state.cues.slice(-(CUE_LIMIT - 1)), { event: e, at: now }],
    ball: state.roster ? nextBall(state.ball, e, state.roster) : state.ball,
  };
  if (e.type === "card" && e.player_id) {
    next.cards = { ...state.cards, [e.player_id]: e.card === "yellow" ? "yellow" : "red" };
  }
  const entry = state.roster ? feedEntry(e, state.roster) : null;
  if (entry && msg.significance > 0) next.moments = topMoments(state.moments, e, msg.significance, entry.text);
  if (!entry || state.feed.some((f) => f.entry_id === entry.entry_id)) return next;
  if (msg.held) return { ...next, held: { ...state.held, [entry.entry_id]: entry } };
  return { ...next, feed: insertEntry(state.feed, entry) };
}

/** "45+2'" is 45.02, "12'" is 12: a sortable match minute from a feed label. */
function minuteValue(label: string): number {
  const [main, extra] = label.replace("'", "").split("+");
  return (Number(main) || 0) + (Number(extra) || 0) / 100;
}

/** Newest first by match minute, so late-arriving lines (revealed, recaps) land in their place. */
function insertEntry(feed: FeedEntry[], entry: FeedEntry): FeedEntry[] {
  const at = minuteValue(entry.minute);
  const index = feed.findIndex((f) => minuteValue(f.minute) <= at);
  const next = index === -1 ? [...feed, entry] : [...feed.slice(0, index), entry, ...feed.slice(index)];
  return next.slice(0, FEED_LIMIT);
}

function topMoments(moments: Moment[], event: MatchEvent, significance: number, text: string): Moment[] {
  if (moments.some((m) => m.event.event_id === event.event_id)) return moments;
  return [...moments, { event, significance, text }]
    .sort((a, b) => b.significance - a.significance || a.event.t - b.event.t)
    .slice(0, MOMENTS);
}

function replaceLine(state: MatchState, msg: FeedReplaceMessage): MatchState {
  const patch = { text: msg.text, ai: msg.ai };
  if (state.feed.some((f) => f.entry_id === msg.entry_id)) {
    return { ...state, feed: state.feed.map((f) => (f.entry_id === msg.entry_id ? { ...f, ...patch } : f)) };
  }
  const held = state.held[msg.entry_id];
  if (held) return { ...state, held: { ...state.held, [msg.entry_id]: { ...held, ...patch } } };
  const kind = msg.event_type.startsWith("period") ? "period" : msg.event_type;
  const entry: FeedEntry = {
    entry_id: msg.entry_id, minute: minuteLabel(msg.clock), icon: iconFor(msg.event_type),
    text: msg.text, tag: has(`tag.${kind}`) ? t(`tag.${kind}`) : t("tag.moment"), ai: msg.ai, tags: [],
  };
  if (msg.held) return { ...state, held: { ...state.held, [msg.entry_id]: entry } };
  return { ...state, feed: insertEntry(state.feed, entry) };
}

function reveal(state: MatchState, ids: string[]): MatchState {
  const held = { ...state.held };
  const revealed: FeedEntry[] = [];
  for (const id of ids) {
    const entry = held[id];
    if (!entry) continue;
    delete held[id];
    revealed.push({ ...entry, tag: t("feed.revealed"), revealed: true });
  }
  if (!revealed.length) return { ...state, held };
  return { ...state, held, feed: revealed.reduce(insertEntry, state.feed) };
}

function explain(state: MatchState, squareId: string, text: string, ai: boolean): MatchState {
  return upsertLine(state, {
    entry_id: `explain:${squareId}`,
    minute: state.anchor ? minuteLabel(state.anchor.clock) : "",
    icon: "💡",
    text,
    tag: t("tag.answer"),
    ai,
    tags: [],
  });
}

/** Adds a line, or replaces one with the same id in place (an AI version of a template). */
function upsertLine(state: MatchState, entry: FeedEntry): MatchState {
  const existing = state.feed.find((f) => f.entry_id === entry.entry_id);
  if (!existing) return { ...state, feed: insertEntry(state.feed, entry) };
  if (existing.ai && !entry.ai) return state;          // never downgrade an AI line
  return { ...state, feed: state.feed.map((f) => (f.entry_id === entry.entry_id ? { ...entry, minute: f.minute } : f)) };
}

function onRecap(state: MatchState, msg: RecapMessage): MatchState {
  const current = state.recaps[msg.kind];
  const catchUp = msg.kind === "catch_up";
  if (!catchUp && current?.ai && !msg.ai) return state;
  const next = { ...state, recaps: { ...state.recaps, [msg.kind]: msg } };
  if (msg.kind !== "halftime" && !catchUp) return next;
  // Every catch-up request is its own line: the template starts one, the AI version fills it.
  const lines = state.feed.filter((f) => f.entry_id.startsWith("recap:catch_up:")).length;
  const id = catchUp ? `recap:catch_up:${msg.ai ? Math.max(lines, 1) : lines + 1}` : `recap:${msg.kind}`;
  return upsertLine(next, {
    entry_id: id,
    minute: state.anchor ? minuteLabel(state.anchor.clock) : "45'",
    icon: "📋",
    text: [msg.content.headline, msg.content.paragraphs[0]].filter(Boolean).join(" "),
    tag: t("tag.recap"),
    ai: msg.ai,
    tags: [],
  });
}

function onStats(state: MatchState, msg: StatsMessage): MatchState {
  const meta = state.meta;
  if (!meta) return { ...state, stats: msg };
  const home = msg.clubs[meta.home_team_id]?.xg;
  const away = msg.clubs[meta.away_team_id]?.xg;
  // While xG is masked the timeline just pauses.
  if (home === null || away === null || home === undefined || away === undefined) {
    return { ...state, stats: msg };
  }
  const point = { t: msg.t, home, away };
  // A jump back in time (dev panel) restarts the timeline from that point.
  const kept = state.xg.filter((p) => p.t < msg.t);
  const last = kept[kept.length - 1];
  const xg = last && last.home === point.home && last.away === point.away ? kept : [...kept, point];
  return { ...state, stats: msg, xg };
}
