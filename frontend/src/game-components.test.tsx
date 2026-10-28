// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockBoard } from "./card/mock";
import type { Board, Square } from "./card/types";
import { AnswerPopover } from "./components/AnswerPopover";
import { Card } from "./components/Card";
import { DevPanel } from "./components/DevPanel";
import { Feed } from "./components/Feed";
import { FullTime } from "./components/FullTime";
import { Leaderboard } from "./components/Leaderboard";
import { Setup } from "./components/Setup";
import { Strategist } from "./components/Strategist";
import { feedEntry } from "./feed/templates";
import type { StrategyAdviceMessage } from "./protocol";
import { buildRoster } from "./roster";
import { setLanguage } from "./i18n";
import { META, ev } from "./test-fixtures";

afterEach(cleanup);

const roster = buildRoster(META);
const find = (id: string) => mockBoard.squares.find((s) => s.id === id)!;
const byText = (text: string) => mockBoard.squares.find((s) => s.text.en === text)!;

function popover(square: Square, extra: Partial<Parameters<typeof AnswerPopover>[0]> = {}) {
  const onAnswer = vi.fn();
  render(<AnswerPopover square={square} roster={roster} language="en" pending={undefined}
    correctAnswer={undefined} onAnswer={onAnswer} onClose={() => {}} {...extra} />);
  return onAnswer;
}

describe("AnswerPopover", () => {
  it("offers the yes/no or range buttons of an open square and sends the value", () => {
    const onAnswer = popover(byText("Will there be a goal by 40'?"));
    fireEvent.click(screen.getByRole("button", { name: /Yes/ }));
    expect(onAnswer).toHaveBeenCalledWith("yes");
  });

  it("number keys pick choices", () => {
    const onAnswer = popover(byText("Will there be a goal by 40'?"));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "2" });
    expect(onAnswer).toHaveBeenCalledWith("no");
  });

  it("lets a first-to-happen square be answered at any time, with the too-early warning", () => {
    const onAnswer = popover(byText("Who is first caught offside?"));
    expect(screen.getByText(/Too early costs your guess/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Kestrel/ }));
    expect(onAnswer).toHaveBeenCalledWith("KVL");
  });

  it("tells you when a waiting deadline square opens", () => {
    popover(byText("Who has more possession at 55'?"));
    expect(screen.getByText("Opens at 55'. Come back then.")).toBeTruthy();
    expect(screen.queryAllByRole("button", { name: /Northbridge/ })).toHaveLength(0);
  });

  it("uses a stepper for exact numbers", () => {
    const square = { ...byText("Will there be a goal by 40'?"), answer_type: "number" as const,
      options: [], option_labels: {} };
    const onAnswer = popover(square);
    fireEvent.click(screen.getByRole("button", { name: "4" }));
    expect(onAnswer).toHaveBeenCalledWith("4");
    fireEvent.click(screen.getByRole("button", { name: "+1" }));
    fireEvent.click(screen.getByRole("button", { name: "+1" }));
    fireEvent.click(screen.getByRole("button", { name: "Answer" }));
    expect(onAnswer).toHaveBeenLastCalledWith("2");
  });

  it("lists starters for player answers and searches the benches", () => {
    const square = { ...byText("Who is first caught offside?"), answer_type: "player" as const,
      options: [], option_labels: {} };
    const onAnswer = popover(square);
    expect(screen.queryByRole("button", { name: /Ludo/ })).toBeNull();     // on the bench
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ludo" } });
    fireEvent.click(screen.getByRole("button", { name: /15 Ludo/ }));
    expect(onAnswer).toHaveBeenCalledWith("NBA-15");
  });

  it("shows what you answered and, once known, the answer", () => {
    popover({ ...find("sq_01"), state: "correct", answer: { value: "0-1", wall_ms: 0, t: 0, elapsed_s: 2 } },
      { correctAnswer: "0-1" });
    expect(screen.getByText("You answered 0–1.")).toBeTruthy();
    expect(screen.getByText("Answer: 0–1")).toBeTruthy();
  });
});

/** The mock board with no open window, so moves are allowed. */
const calm: Board = {
  ...mockBoard,
  squares: mockBoard.squares.map((s) => (s.state === "open" ? { ...s, state: "waiting", closes_at: null } : s)),
};

describe("Card interaction", () => {
  it("selects a square to answer it", () => {
    const onSelect = vi.fn();
    render(<Card board={mockBoard} roster={roster} onSelect={onSelect} onMove={() => {}} />);
    fireEvent.click(screen.getByLabelText(/Who is first caught offside\?/));
    expect(onSelect).toHaveBeenCalledWith("sq_09");
  });

  it("picks up a blank and drops it on a waiting square with the keyboard", () => {
    const onMove = vi.fn();
    render(<Card board={calm} roster={roster} onMove={onMove} />);
    const cells = screen.getAllByRole("gridcell");
    fireEvent.keyDown(cells[4], { key: "Enter" });                 // the blank at row 0, col 4
    expect(screen.getByText(/Pick a waiting square/)).toBeTruthy();
    expect(cells[9].className).toContain("drop-target");            // waiting first square
    expect(cells[1].className).not.toContain("drop-target");        // resolved
    fireEvent.keyDown(cells[9], { key: "Enter" });
    expect(onMove).toHaveBeenCalledWith({ row: 0, col: 4 }, { row: 1, col: 4 });
  });

  it("won't pick anything up while an announced window is open", () => {
    const onMove = vi.fn();
    render(<Card board={mockBoard} roster={roster} onMove={onMove} />);
    const cells = screen.getAllByRole("gridcell");
    fireEvent.keyDown(cells[4], { key: "Enter" });
    expect(screen.getByText("No moves while a window is open.")).toBeTruthy();
    expect(cells[4].getAttribute("draggable")).toBe("false");
  });

  it("outlines the strategist's suggested move", () => {
    const advice: StrategyAdviceMessage = { type: "strategy.advice", t: 0, wall: 0, advice_id: "a",
      before: 0.2, after: 0.5, reason: "r", applied: false,
      moves: [{ from_cell: { row: 0, col: 4 }, to_cell: { row: 1, col: 4 } }] };
    render(<Card board={calm} roster={roster} advice={advice} />);
    const cells = screen.getAllByRole("gridcell");
    expect(cells[4].className).toContain("advice-from");
    expect(cells[9].className).toContain("advice-to");
  });
});

describe("Feed masks", () => {
  it("collapses lines an open square depends on", () => {
    const entries = [ev("foul", { tags: ["fouls"] }), ev("corner", { tags: ["corners"] })]
      .map((e) => feedEntry(e, roster)!);
    render(<Feed entries={entries} masked={new Set(["fouls"])} />);
    const items = within(screen.getByRole("log")).getAllByRole("listitem");
    expect(items[0].textContent).toContain("Hidden while a square is open");
    expect(items[1].textContent).toContain("Corner to Northbridge.");
  });
});

describe("Strategist and leaderboard", () => {
  it("offers Apply with the chance before and after", () => {
    const onApply = vi.fn();
    render(<Strategist note={null} onApply={onApply} advice={{ type: "strategy.advice", t: 0, wall: 0,
      advice_id: "a7", before: 0.41, after: 0.58, reason: "Moved a blank into row 3.", applied: false,
      moves: [] }} />);
    expect(screen.getByText("Chance of a line: 41% → 58%")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onApply).toHaveBeenCalledWith("a7");
  });

  it("marks your row", () => {
    render(<Leaderboard mode="normal" rows={[
      { rank: 1, handle: "BlueScarf_22", points: 900, correct: 6, avg_answer_s: 4.2, you: false },
      { rank: 7, handle: "Sam", points: 300, correct: 2, avg_answer_s: null, you: true }]} />);
    const rows = screen.getAllByRole("row");
    expect(rows[2].className).toBe("you");
    expect(rows[2].textContent).toContain("(you)");
    expect(rows[1].textContent).toContain("4.2 s");
  });
});

describe("Setup", () => {
  it("sends the chosen profile on kick-off", () => {
    const onKickoff = vi.fn();
    render(<Setup meta={META} seed={2610} onKickoff={onKickoff} />);
    fireEvent.click(screen.getByLabelText(/Advanced/));
    fireEvent.click(screen.getByLabelText("Kestrel Vale"));
    fireEvent.change(screen.getByLabelText(/Focus player/), { target: { value: "NBA-09" } });
    fireEvent.click(screen.getByRole("button", { name: "Kick off" }));
    expect(onKickoff).toHaveBeenCalledWith({ seed: 2610, profile: { mode: "advanced", club: "KVL",
      focus_player_id: "NBA-09", handle: "You", language: "en" } });
  });

  it("switches to French and sends the language with the profile", () => {
    const onKickoff = vi.fn();
    render(<Setup meta={META} seed={2610} onKickoff={onKickoff} />);
    fireEvent.click(screen.getByLabelText("Français"));
    expect(screen.getByRole("button", { name: "Coup d'envoi" })).toBeTruthy();
    expect(screen.getByText("Comment jouer")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Coup d'envoi" }));
    expect(onKickoff.mock.calls[0][0].profile.language).toBe("fr");
    setLanguage("en");
  });
});

describe("FullTime", () => {
  it("summarises the card and your rank", () => {
    render(<FullTime roster={roster} score={{ NBA: 1, KVL: 1 }} board={mockBoard} moments={[]}
      leaderboard={[{ rank: 4, handle: "You", points: 1342, correct: 6, avg_answer_s: 3, you: true }]}
      total={21} mode="normal" onClose={() => {}} />);
    expect(screen.getByText("Northbridge Athletic 1 – 1 Kestrel Vale")).toBeTruthy();
    expect(screen.getByText(/6 correct, 2 wrong, 1 missed · 1 lines · 1,342 points/)).toBeTruthy();
    expect(screen.getByText("You finished 4 of 21 on the Normal leaderboard.")).toBeTruthy();
  });
});

describe("DevPanel", () => {
  it("pauses, jumps, flips the failure switch and shows agent health", () => {
    const onPause = vi.fn();
    const onJump = vi.fn();
    const onNarratorDown = vi.fn();
    const agent = { calls: 12, ai: 9, fallbacks: 3, timeouts: 1, errors: 0, verifier_failures: 2,
      per_minute: 7, latency_ms: 1640, breaker: "forced" as const, trips: 0, skipped: 1 };
    render(<DevPanel paused={false} narratorDown={false} onPause={onPause} onJump={onJump}
      onNarratorDown={onNarratorDown} health={{ type: "health", t: 0, wall: 0, online: true,
        agents: { narrator: agent }, llm_calls_per_minute: 7, events_per_minute: 120 }} />);
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(onPause).toHaveBeenCalledWith(true);
    fireEvent.change(screen.getByLabelText(/Jump to minute/), { target: { value: "62" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(onJump).toHaveBeenCalledWith(62);
    fireEvent.click(screen.getByLabelText(/Narrator offline/));
    expect(onNarratorDown).toHaveBeenCalledWith(true);
    const row = screen.getByRole("row", { name: /narrator/ });
    expect(row.textContent).toContain("forced open");
    expect(row.textContent).toContain("1640 ms");
    expect(screen.getByText("7 LLM calls/min · 120 events/min")).toBeTruthy();
  });
});

describe("Card accessibility", () => {
  it("names each cell on the gridcell itself", () => {
    render(<Card board={mockBoard} roster={roster} />);
    const cell = screen.getByLabelText(/Who is first caught offside\?/);
    expect(cell.getAttribute("role")).toBe("gridcell");
  });
});
