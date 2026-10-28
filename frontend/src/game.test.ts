import { describe, expect, it } from "vitest";
import { mockBoard } from "./card/mock";
import { announcedOpen, canMove } from "./card/rules";
import type { Board, Square, SquareKind, SquareState } from "./card/types";
import type { ServerMessage, StrategyAdviceMessage } from "./protocol";
import { initialState, maskedTags, matchReducer, type MatchState } from "./state/match";
import { META, PROFILE, ev } from "./test-fixtures";

const BLANK = { row: 0, col: 4 };      // an empty blank in the mock board
const OTHER = { row: 4, col: 4 };      // another empty blank

/** A copy of the mock board with no scored lines and no open window, then edits. */
function board(edit: (squares: Square[]) => void = () => {}): Board {
  const squares = mockBoard.squares.map((s) => ({ ...s, closes_at: null,
    state: s.state === "open" ? ("waiting" as SquareState) : s.state }));
  edit(squares);
  return { ...mockBoard, squares, scored_lines: [] };
}

const at = (squares: Square[], row: number, col: number) =>
  squares.find((s) => s.cell.row === row && s.cell.col === col)!;

function set(squares: Square[], row: number, col: number, kind: SquareKind, state: SquareState) {
  const sq = at(squares, row, col);
  sq.kind = kind;
  sq.state = state;
}

// Mirrors backend/tests/test_game_moves.py.
describe("move rules", () => {
  const TARGET = { row: 2, col: 3 };   // a waiting deadline square in the mock board

  it.each<[SquareState, boolean]>([
    ["empty_blank", true], ["wildcard", true], ["wrong", false], ["missed", false], ["waiting", false],
  ])("picking up a %s square: %s", (state, allowed) => {
    const b = board((s) => set(s, BLANK.row, BLANK.col, state === "waiting" ? "deadline" : "live", state));
    expect(canMove(b, BLANK, TARGET)).toBe(allowed);
  });

  it.each<[SquareKind, SquareState, boolean]>([
    ["deadline", "waiting", true], ["first", "waiting", true], ["live", "empty_blank", true],
    ["live", "wildcard", true], ["deadline", "correct", false], ["deadline", "wrong", false],
    ["deadline", "missed", false], ["first", "void", false], ["first", "too_early", false],
    ["live", "wrong", false], ["live", "missed", false],
  ])("a %s %s target: %s", (kind, state, allowed) => {
    const b = board((s) => set(s, TARGET.row, TARGET.col, kind, state));
    expect(canMove(b, BLANK, TARGET)).toBe(allowed);
  });

  it("a static can never be picked up, and a cell can't swap with itself", () => {
    expect(canMove(board(), TARGET, BLANK)).toBe(false);
    expect(canMove(board(), BLANK, BLANK)).toBe(false);
  });

  it("an open announced window blocks every move", () => {
    const b = board((s) => {
      at(s, 1, 3).state = "open";
      at(s, 1, 3).closes_at = Date.now() + 10_000;
    });
    expect(announcedOpen(b)).toBe(true);
    expect(canMove(b, BLANK, TARGET)).toBe(false);
  });

  it("a first-to-happen square in its silent window looks waiting and takes a swap", () => {
    // The server sends it as waiting with no closes_at, so the card can't tell.
    expect(canMove(board(), BLANK, { row: 1, col: 4 })).toBe(true);
  });

  it("locked squares neither move nor take a swap", () => {
    const scored = { ...board((s) => set(s, 0, 0, "live", "wildcard")), scored_lines: ["col:0"] };
    expect(canMove(scored, { row: 0, col: 0 }, TARGET)).toBe(false);
    expect(canMove(scored, BLANK, { row: 1, col: 0 })).toBe(false);
    expect(canMove(scored, BLANK, OTHER)).toBe(true);
  });
});

function ready(): MatchState {
  return send(initialState, {
    type: "session.ready", t: 0, wall: 0, session_id: "s1", match: META, profile: PROFILE,
    card: board(), speed: 1, paused: false, duration: 5900,
  });
}

function send(state: MatchState, ...msgs: ServerMessage[]): MatchState {
  return msgs.reduce((s, msg) => matchReducer(s, { kind: "message", msg, now: 1 }), state);
}

const square = (state: MatchState, id: string) => state.board!.squares.find((s) => s.id === id)!;

describe("game reducer", () => {
  it("opens an announced window and reads it out", () => {
    const state = send(ready(), { type: "square.window_open", t: 900, wall: 0, square_id: "sq_01",
      closes_at: 123 });
    expect(square(state, "sq_01")).toMatchObject({ state: "open", closes_at: 123 });
    expect(state.announcement).toContain("How many yellow cards by 15'?");
  });

  it("marks an answer pending until its result, then shows the result", () => {
    let state = matchReducer(ready(), { kind: "answer", squareId: "sq_01", value: "0-1" });
    expect(state.pending).toEqual({ sq_01: "0-1" });
    state = send(state, { type: "square.result", t: 905, wall: 0, square_id: "sq_01",
      status: "correct", points: 100, correct_answer: "0-1" });
    expect(state.pending).toEqual({});
    expect(square(state, "sq_01")).toMatchObject({ state: "correct", result: { points: 100 } });
    expect(state.answers.sq_01).toBe("0-1");
  });

  it("turns a correct live square into a wildcard", () => {
    const live = { ...square(ready(), "blank_04"), state: "open" as SquareState, text: { en: "Q?" } };
    const state = send(ready(), { type: "square.added", t: 600, wall: 0, square: live },
      { type: "square.result", t: 601, wall: 0, square_id: live.id, status: "correct", points: 150,
        correct_answer: "foul" });
    expect(square(state, live.id).state).toBe("wildcard");
    expect(state.announcement).toContain("Live square: Q?");
  });

  it("a refused answer frees the square to try again", () => {
    let state = matchReducer(ready(), { kind: "answer", squareId: "sq_01", value: "x" });
    state = send(state, { type: "error", t: 1, wall: 0, request: "answer.submit", reason: "nope" });
    expect(state.pending).toEqual({});
    expect(state.notice).toMatchObject({ text: "nope", kind: "error" });
  });

  it("holds masked feed lines and reveals them later", () => {
    const foul = ev("foul", { tags: ["fouls"] });
    let state = send(ready(),
      { type: "mask.on", t: 0, wall: 0, square_id: "sq_03", tags: ["fouls"] },
      { type: "event", t: 10, wall: 0, event: foul, significance: 25, held: true });
    expect(maskedTags(state)).toEqual(new Set(["fouls"]));
    expect(state.feed).toEqual([]);
    expect(state.cues).toEqual([]);                      // no cue for a held event
    state = send(state, { type: "mask.off", t: 30, wall: 0, square_id: "sq_03", tags: ["fouls"] },
      { type: "feed.reveal", t: 30, wall: 0, entry_ids: [foul.event_id] });
    expect(maskedTags(state).size).toBe(0);
    expect(state.feed[0]).toMatchObject({ entry_id: foul.event_id, tag: "Revealed", revealed: true });
  });

  it("posts explanations to the feed once", () => {
    const msg = { type: "square.explanation", t: 920, wall: 0, square_id: "sq_01",
      text: "How many yellow cards by 15'? Answer: 0–1." } as const;
    const state = send(ready(), msg, msg);
    expect(state.feed.map((f) => f.text)).toEqual([msg.text]);
  });

  it("replaces the board on board.update", () => {
    const next = board((s) => set(s, 2, 3, "deadline", "correct"));
    const state = send(ready(), { type: "board.update", t: 1, wall: 0, ...next, points: 500 });
    expect(state.board!.points).toBe(500);
    expect(at(state.board!.squares, 2, 3).state).toBe("correct");
  });

  it("keeps suggested advice until applied, and notes automatic moves", () => {
    const advice: StrategyAdviceMessage = { type: "strategy.advice", t: 1, wall: 0, advice_id: "a1",
      before: 0.4, after: 0.6, reason: "Moved a blank into row 2.", applied: false,
      moves: [{ from_cell: BLANK, to_cell: OTHER }] };
    let state = send(ready(), { ...advice, applied: false });
    expect(state.advice?.advice_id).toBe("a1");
    state = matchReducer(state, { kind: "moved" });
    expect(state.advice).toBeNull();
    state = send(state, { ...advice, applied: true });
    expect(state.strategistNote).toBe("Moved a blank into row 2.");
  });

  it("keeps the three biggest moments", () => {
    let state = ready();
    for (const [type, sig] of [["foul", 25], ["goal", 90], ["offside", 40], ["corner", 10], ["shot", 70]] as const) {
      const e = ev(type, { outcome: "saved", scorer_id: "NBA-09" });
      state = send(state, { type: "event", t: e.t, wall: 0, event: e, significance: sig, held: false });
    }
    expect(state.moments.map((m) => m.significance)).toEqual([90, 70, 40]);
  });

  it("stores leaderboard rows and the field size", () => {
    const state = send(ready(), { type: "leaderboard", t: 1, wall: 0, mode: "normal", total: 21,
      rows: [{ rank: 1, handle: "You", points: 100, correct: 1, avg_answer_s: 2, you: true }] });
    expect(state.leaderboard).toHaveLength(1);
    expect(state.ranked).toBe(21);
  });
});

describe("AI feed lines", () => {
  const replace = (id: string, held = false): ServerMessage => ({
    type: "feed.replace", t: 30, wall: 0, entry_id: id, text: "AI line.", ai: true,
    clock: "00:30", event_type: "pressure", held,
  });

  it("replaces a template line in place and marks it AI", () => {
    const corner = ev("corner", { clock: "00:30" });
    let state = send(ready(), { type: "event", t: 30, wall: 0, event: corner, significance: 45, held: false });
    state = send(state, replace(corner.event_id));
    expect(state.feed).toHaveLength(1);
    expect(state.feed[0]).toMatchObject({ entry_id: corner.event_id, text: "AI line.", ai: true, tag: "Corner" });
  });

  it("adds a line for a moment with no template, and keeps a held one back", () => {
    let state = send(ready(), replace("e9"));
    expect(state.feed[0]).toMatchObject({ entry_id: "e9", minute: "1'", tag: "Moment", ai: true });
    state = send(state, replace("e10", true));
    expect(state.feed.map((f) => f.entry_id)).toEqual(["e9"]);
    state = send(state, { type: "feed.reveal", t: 50, wall: 0, entry_ids: ["e10"] });
    expect(state.feed[0]).toMatchObject({ entry_id: "e10", text: "AI line.", tag: "Revealed" });
  });

  it("updates a held template line so the reveal shows the AI text", () => {
    const foul = ev("foul", { tags: ["fouls"] });
    let state = send(ready(), { type: "event", t: 10, wall: 0, event: foul, significance: 45, held: true });
    state = send(state, replace(foul.event_id, true),
      { type: "feed.reveal", t: 40, wall: 0, entry_ids: [foul.event_id] });
    expect(state.feed[0]).toMatchObject({ text: "AI line.", ai: true, revealed: true });
  });
});

describe("explanations and recaps", () => {
  it("replaces a template explanation with the AI one, never the other way", () => {
    const base = { type: "square.explanation", t: 0, wall: 0, square_id: "sq_01" } as const;
    let state = send(ready(), { ...base, text: "Template." }, { ...base, text: "Tutor line.", ai: true });
    expect(state.feed.map((f) => [f.text, f.ai])).toEqual([["Tutor line.", true]]);
    state = send(state, { ...base, text: "Template." });
    expect(state.feed[0].text).toBe("Tutor line.");
  });

  it("posts the half-time recap to the feed and keeps the full-time one for the screen", () => {
    const content = { headline: "Half-time: Northbridge 1–0 Kestrel", paragraphs: ["Goals: Arvel."],
      talking_points: ["a", "b", "c"], club_paragraph: null, player_paragraph: null, bingo_summary: null };
    let state = send(ready(), { type: "recap", t: 0, wall: 0, kind: "halftime", content, ai: false });
    expect(state.feed[0]).toMatchObject({ entry_id: "recap:halftime", tag: "Recap",
      text: "Half-time: Northbridge 1–0 Kestrel Goals: Arvel." });
    state = send(state, { type: "recap", t: 0, wall: 0, kind: "full_time", content, ai: true });
    expect(state.recaps.full_time?.ai).toBe(true);
    state = send(state, { type: "recap", t: 0, wall: 0, kind: "full_time", content, ai: false });
    expect(state.recaps.full_time?.ai).toBe(true);
  });
});

describe("definitions and catch-up", () => {
  it("shows the stored definition, then the tutor's, only for the term asked", () => {
    let state = matchReducer(ready(), { kind: "define", term: "ppda" });
    state = send(state,
      { type: "definition", t: 0, wall: 0, term: "xg", text: "Other.", ai: false },
      { type: "definition", t: 0, wall: 0, term: "ppda", text: "Stored.", ai: false },
      { type: "definition", t: 0, wall: 0, term: "ppda", text: "Tutor.", ai: true },
      { type: "definition", t: 0, wall: 0, term: "ppda", text: "Stored.", ai: false });
    expect(state.definition).toEqual({ term: "ppda", text: "Tutor.", ai: true });
    expect(matchReducer(state, { kind: "define", term: null }).definition).toBeNull();
  });

  it("posts a catch-up recap to the feed", () => {
    const content = { headline: "Catch-up: Northbridge 0–0 Kestrel", paragraphs: ["No goals yet."],
      talking_points: ["a", "b", "c"], club_paragraph: null, player_paragraph: null, bingo_summary: null };
    const state = send(ready(), { type: "recap", t: 0, wall: 0, kind: "catch_up", content, ai: false });
    expect(state.feed[0]).toMatchObject({ entry_id: "recap:catch_up", text: "Catch-up: Northbridge 0–0 Kestrel No goals yet." });
  });
});
