// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockBoard } from "./card/mock";
import { Card } from "./components/Card";
import { Feed } from "./components/Feed";
import { Metrics, topPerformer } from "./components/Metrics";
import { TopBar, halfLabel } from "./components/TopBar";
import { feedEntry } from "./feed/templates";
import { META, ev } from "./test-fixtures";
import type { StatsMessage } from "./protocol";
import { buildRoster } from "./roster";
import { FrameStore } from "./state/frames";

afterEach(cleanup);

const roster = buildRoster(META);

const club = (extra: object) => ({
  possession: 50, shots: 0, shots_on_target: 0, passes: 0, passes_completed: 0, pass_accuracy: null,
  corners: 0, fouls: 0, yellow_cards: 0, red_cards: 0, offsides: 0, tackles_won: 0, interceptions: 0,
  duels_won: 0, xg: 0, ...extra,
});

const STATS = {
  type: "stats", t: 600, wall: 0, score: { NBA: 1, KVL: 0 }, ball_in_play_s: 400,
  clubs: { NBA: club({ possession: 61.5, shots: 5, shots_on_target: 2, xg: 0.84 }), KVL: club({ possession: 38.5, xg: 0.12 }) },
  players: {
    "NBA-09": { team_id: "NBA", touches: 31, passes: 20, passes_completed: 17, shots: 3, xg: 0.6, tackles: 0,
      duels_won: 2, distance_km: 1.2, top_speed_kmh: 31, sprints: 2 },
    "KVL-04": { team_id: "KVL", touches: 12, passes: 9, passes_completed: 8, shots: 0, xg: 0, tackles: 2,
      duels_won: 1, distance_km: 1, top_speed_kmh: 28, sprints: 0 },
  },
  patterns: {
    chaos: { value: 72.4, in_control: "NBA" },
    pressure: { NBA: { ppda: 6.2, pressing_height_m: 50, field_tilt: 64, high_regains: 2, high_regains_5min: 1 },
      KVL: { ppda: 11.8, pressing_height_m: 40, field_tilt: 36, high_regains: 0, high_regains_5min: 0 } },
    rhythm: { events_per_min: 33, passes_per_min: 10, since_stoppage_s: 40, in_play_share: 66, tempo: "Steady" },
    momentum: { value: 34, threat: { NBA: 2, KVL: 1 } },
  },
} as unknown as StatsMessage;

describe("TopBar", () => {
  it("shows the score and switches speed", () => {
    const onSpeed = vi.fn();
    render(<TopBar roster={roster} score={{ NBA: 2, KVL: 1 }} anchor={{ t: 0, clock: "00:00", period: 1 }}
      fullTime={false} frames={new FrameStore()} speed={1} onSpeed={onSpeed} mode="normal" onMode={() => {}} />);
    expect(screen.getByText("Northbridge 2, Kestrel 1")).toBeTruthy();
    const speed = screen.getByRole("group", { name: "Replay speed" });
    expect(within(speed).getByRole("button", { name: "1x" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(within(speed).getByRole("button", { name: "10x" }));
    expect(onSpeed).toHaveBeenCalledWith(10);
  });

  it("labels the half", () => {
    expect(halfLabel(null, false)).toBe("Kick-off");
    expect(halfLabel({ t: 3000, clock: "50:00", period: 2 }, false)).toBe("2nd half");
    expect(halfLabel({ t: 5900, clock: "90+4:00", period: 2 }, true)).toBe("Full time");
  });
});

describe("Feed", () => {
  it("is a polite live region with the newest entry first", () => {
    const entries = [ev("corner", { clock: "30:00" }), ev("foul", { clock: "20:00" })]
      .map((e) => feedEntry(e, roster)!);
    render(<Feed entries={entries} />);
    const log = screen.getByRole("log");
    expect(log.getAttribute("aria-live")).toBe("polite");
    const items = within(log).getAllByRole("listitem");
    expect(items[0].textContent).toContain("Corner to Northbridge.");
    expect(items[1].textContent).toContain("Foul by Arvel of Northbridge.");
  });
});

describe("Metrics", () => {
  it("shows the normal-mode stats and keeps advanced ones back", () => {
    render(<Metrics roster={roster} stats={STATS} xg={[]} mode="normal" />);
    expect(screen.getByRole("img", { name: /Possession: Northbridge 62%, Kestrel 39%/ })).toBeTruthy();
    expect(screen.getByRole("row", { name: /Shots \(on target\) 5 \(2\) 0 \(0\)/ })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Momentum: Northbridge +34" })).toBeTruthy();
    expect(screen.getByRole("meter", { name: "Control vs. chaos" }).getAttribute("aria-valuenow")).toBe("72.4");
    expect(screen.queryByText(/Expected goals/)).toBeNull();
  });

  it("adds xG, pressure and the top performer in advanced mode", () => {
    render(<Metrics roster={roster} stats={STATS} xg={[{ t: 300, home: 0.84, away: 0.12 }]} mode="advanced" />);
    expect(screen.getByRole("row", { name: /Expected goals \(xG\) 0.84 0.12/ })).toBeTruthy();
    expect(screen.getByRole("row", { name: /Field tilt 64% 36%/ })).toBeTruthy();
    expect(screen.getByText(/Arvel \(Northbridge\): 31 touches, 17\/20 passes/)).toBeTruthy();
    expect(topPerformer(STATS)).toBe("NBA-09");
  });
});

describe("Card", () => {
  it("lays out 25 cells with dashed blanks and labelled states", () => {
    render(<Card board={mockBoard} />);
    const cells = screen.getAllByRole("gridcell");
    expect(cells).toHaveLength(25);
    expect(screen.getAllByLabelText("Blank: a live question will land here")).toHaveLength(3);
    expect(screen.getByLabelText(/Will there be a goal by 40'\?\. at 40'\. Open\. \d+ seconds left/)).toBeTruthy();
    expect(screen.getByLabelText(/How does play restart\?\. Wildcard\. In a scored line/)).toBeTruthy();
    expect(screen.getByText("1,342")).toBeTruthy();
  });

  it("moves focus with the arrow keys and stays on the card", () => {
    render(<Card board={mockBoard} />);
    const cells = screen.getAllByRole("gridcell");
    cells[0].focus();
    fireEvent.keyDown(cells[0], { key: "ArrowRight" });
    expect(document.activeElement).toBe(cells[1]);
    fireEvent.keyDown(cells[1], { key: "ArrowDown" });
    expect(document.activeElement).toBe(cells[6]);
    fireEvent.keyDown(cells[6], { key: "ArrowUp" });
    fireEvent.keyDown(cells[1], { key: "ArrowUp" });
    expect(document.activeElement).toBe(cells[1]);
    cells[4].focus();
    fireEvent.keyDown(cells[4], { key: "ArrowRight" });
    expect(document.activeElement).toBe(cells[4]);
    expect(cells.filter((c) => c.tabIndex === 0)).toHaveLength(1);
  });
});
