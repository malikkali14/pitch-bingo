import { describe, expect, it } from "vitest";
import { clockAt, formatClock, minuteLabel, periodElapsed } from "./clock";
import { deadlineLabel, isLocked, linesOf } from "./card/types";
import { mockBoard } from "./card/mock";
import { feedEntry } from "./feed/templates";
import type { FrameMessage, MatchEvent, StatsMessage } from "./protocol";
import { carrierAt, initialBall, nextBall } from "./state/ball";
import { META, ev } from "./test-fixtures";
import { buildRoster } from "./roster";
import { FrameStore, lerpFrames } from "./state/frames";
import { initialState, matchReducer, type MatchState } from "./state/match";

function ready(): MatchState {
  return matchReducer(initialState, {
    kind: "message", now: 0,
    msg: { type: "session.ready", t: 0, wall: 0, session_id: "s1", match: META, profile: {},
      card: null, speed: 1, paused: false, duration: 5900 },
  });
}

describe("clock", () => {
  it.each([
    ["00:04", 1, 4], ["23:15", 1, 1395], ["45+2:10", 1, 2830], ["45:00", 2, 0], ["67:30", 2, 1350],
    ["90+5:51", 2, 3051],
  ])("%s in period %i is %i s into the period", (clock, period, seconds) => {
    expect(periodElapsed(clock, period)).toBe(seconds);
  });

  it.each([
    [4, 1, "00:04"], [2700, 1, "45:00"], [2830, 1, "45+2:10"], [0, 2, "45:00"], [1350, 2, "67:30"],
    [3051, 2, "90+5:51"],
  ])("formats %i s in period %i as %s", (seconds, period, text) => {
    expect(formatClock(seconds, period)).toBe(text);
  });

  it("advances the last event's clock by match time", () => {
    expect(clockAt({ t: 3000, clock: "46:30", period: 2 }, 3012.4)).toBe("46:42");
    expect(clockAt(null, 75)).toBe("01:15");
  });

  it("labels minutes the football way", () => {
    expect(minuteLabel("00:04")).toBe("1'");
    expect(minuteLabel("23:15")).toBe("24'");
    expect(minuteLabel("45+2:10")).toBe("45+3'");
  });
});

describe("feed templates", () => {
  const roster = buildRoster(META);

  it("writes a goal line with the scorer and club", () => {
    const entry = feedEntry(ev("goal", { scorer_id: "NBA-09", clock: "15:54" }), roster);
    expect(entry).toMatchObject({ minute: "16'", text: "GOAL! Arvel scores for Northbridge.", tag: "Goal", ai: false });
  });

  it("names both players in a substitution", () => {
    const entry = feedEntry(ev("substitution", { player_on_id: "NBA-15", player_off_id: "NBA-09" }), roster);
    expect(entry?.text).toBe("Northbridge substitution: Ludo comes on for Arvel.");
  });

  it("uses a red icon for a second yellow", () => {
    expect(feedEntry(ev("card", { card: "second_yellow" }), roster)?.icon).toBe("🟥");
    expect(feedEntry(ev("card", { card: "yellow" }), roster)?.icon).toBe("🟨");
  });

  it("skips routine events and the shot behind a goal", () => {
    expect(feedEntry(ev("pass"), roster)).toBeNull();
    expect(feedEntry(ev("possession_change"), roster)).toBeNull();
    expect(feedEntry(ev("shot", { outcome: "goal" }), roster)).toBeNull();
    expect(feedEntry(ev("shot", { outcome: "saved" }), roster)?.text).toBe(
      "Arvel shoots for Northbridge, and it's saved.");
  });
});

describe("match reducer", () => {
  it("builds the feed newest first, once per event", () => {
    let state = ready();
    const foul = ev("foul", { t: 20, clock: "00:20" });
    const corner = ev("corner", { t: 30, clock: "00:30" });
    for (const e of [foul, ev("pass"), corner, corner]) {
      state = matchReducer(state, { kind: "message", now: 1, msg: { type: "event", t: e.t, wall: 0, event: e, significance: 0 } });
    }
    expect(state.feed.map((f) => f.entry_id)).toEqual([corner.event_id, foul.event_id]);
    expect(state.cues).toHaveLength(4);
    expect(state.anchor).toEqual({ t: 30, clock: "00:30", period: 1 });
  });

  it("keeps card badges and marks full time", () => {
    let state = ready();
    for (const e of [ev("card", { card: "yellow", player_id: "KVL-04" }),
      ev("card", { card: "second_yellow", player_id: "KVL-04" }),
      ev("period_end", { period: 2, t: 5900, clock: "90+4:00" })]) {
      state = matchReducer(state, { kind: "message", now: 1, msg: { type: "event", t: e.t, wall: 0, event: e, significance: 0 } });
    }
    expect(state.cards).toEqual({ "KVL-04": "red" });
    expect(state.fullTime).toBe(true);
  });

  it("records an xG point only when xG changes, and restarts after a jump back", () => {
    let state = ready();
    const stats = (t: number, home: number, away: number) =>
      ({ type: "stats", t, wall: 0, score: {}, ball_in_play_s: 0, players: {},
        clubs: { NBA: { xg: home }, KVL: { xg: away } },
        patterns: {} } as unknown as StatsMessage);
    for (const [t, h, a] of [[1, 0, 0], [2, 0, 0], [60, 0.1, 0], [120, 0.1, 0.3]]) {
      state = matchReducer(state, { kind: "message", now: 0, msg: stats(t, h, a) });
    }
    expect(state.xg.map((p) => p.t)).toEqual([1, 60, 120]);
    state = matchReducer(state, { kind: "message", now: 0, msg: stats(50, 0, 0) });
    expect(state.xg.map((p) => p.t)).toEqual([1]);
  });
});

describe("frames", () => {
  const frame = (t: number, x: number): FrameMessage => ({
    type: "frame", t, wall: 0, ball: [x, 34, 0], players: [["NBA-09", x, 30]],
  });

  it("interpolates between the last two frames", () => {
    const p = lerpFrames(frame(1, 10), frame(1.1, 20), 0.25);
    expect(p.players.get("NBA-09")).toEqual([12.5, 30]);
    expect(p.ball[0]).toBe(12.5);
  });

  it("glides one frame behind, and snaps after a jump", () => {
    const store = new FrameStore();
    store.push(frame(1, 10), 1000);
    store.push(frame(1.1, 20), 1100);
    expect(store.at(1150)?.players.get("NBA-09")).toEqual([15, 30]);
    expect(store.at(1150, false)?.players.get("NBA-09")).toEqual([20, 30]);
    store.push(frame(600, 80), 1200);
    expect(store.at(1210)?.players.get("NBA-09")).toEqual([80, 30]);
  });
});

describe("mock card", () => {
  it("follows the card rules it will be swapped for", () => {
    const squares = mockBoard.squares;
    expect(squares).toHaveLength(25);
    expect(new Set(squares.map((s) => `${s.cell.row},${s.cell.col}`)).size).toBe(25);
    const kinds = (k: string) => squares.filter((s) => s.kind === k).length;
    expect(kinds("live")).toBe(5);
    expect(kinds("deadline") + kinds("first")).toBe(20);
    for (const s of squares) expect((s.text.en ?? "").length).toBeLessThanOrEqual(60);
  });

  it("knows which lines a cell sits on", () => {
    expect(linesOf({ row: 2, col: 2 })).toEqual(["row:2", "col:2", "diag:0", "diag:1"]);
    const corner = mockBoard.squares.find((s) => s.cell.row === 4 && s.cell.col === 0)!;
    expect(isLocked(corner, mockBoard)).toBe(true);
  });

  it("labels deadlines", () => {
    expect(deadlineLabel(4200)).toBe("70'");
    expect(deadlineLabel(2700)).toBe("45:00");
    expect(deadlineLabel(5400)).toBe("90:00");
  });
});

describe("ball state", () => {
  const roster = buildRoster(META);
  const run = (...events: MatchEvent[]) => events.reduce((b, e) => nextBall(b, e, roster), initialBall);

  it("follows the ball from passer to receiver once the pass lands", () => {
    const ball = run(ev("carry", { player_id: "NBA-09" }),
      ev("pass", { t: 20, player_id: "NBA-09", receiver_id: "NBA-15", outcome: "complete",
        length_m: 20, ball_speed_kmh: 72 }));
    expect(carrierAt(ball, 20.5)).toBeNull();          // in the air: 20 m at 20 m/s
    expect(carrierAt(ball, 21)).toBe("NBA-15");
  });

  it("drops the carrier on a shot or a misplaced pass", () => {
    expect(carrierAt(run(ev("carry"), ev("shot", { outcome: "saved" })), 20)).toBeNull();
    expect(carrierAt(run(ev("carry"), ev("pass", { outcome: "incomplete", receiver_id: "NBA-15",
      length_m: 10, ball_speed_kmh: 50 })), 30)).toBeNull();
  });

  it.each([
    // [event, expected note]: home attacks x = 105 in the first half
    [ev("out_of_play", { x: 40, y: 0, last_touch_team_id: "NBA" }), "Ball out: Kestrel throw-in"],
    [ev("out_of_play", { x: 105, y: 20, last_touch_team_id: "KVL" }), "Ball out: corner to Northbridge"],
    [ev("out_of_play", { x: 105, y: 20, last_touch_team_id: "NBA" }), "Ball out: Kestrel goal kick"],
    [ev("out_of_play", { x: 0, y: 20, period: 2, last_touch_team_id: "KVL" }), "Ball out: corner to Northbridge"],
    [ev("foul", { team_id: "KVL", advantage: false }), "Foul: Northbridge free kick"],
    [ev("offside", { team_id: "NBA" }), "Offside: Kestrel free kick"],
    [ev("goal", { team_id: "NBA" }), "Goal! Kestrel to kick off"],
    [ev("period_end", { period: 1 }), "Half-time"],
  ])("explains a stoppage", (event, note) => {
    expect(run(event).stoppage).toBe(note);
  });

  it("clears the note when play restarts, but not for advantage", () => {
    expect(run(ev("foul", { team_id: "KVL", advantage: true })).stoppage).toBeNull();
    expect(run(ev("out_of_play", { x: 40, y: 0, last_touch_team_id: "NBA" }),
      ev("throw_in", { team_id: "KVL", player_id: "KVL-04" })).stoppage).toBeNull();
  });
});
