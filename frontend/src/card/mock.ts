// Test fixture: a board in the server's shape (backend/app/game/card.py) showing every square
// state from spec 4.3 at once: a scored column, an open window, and three empty blanks.

import type { Board, Square, SquareKind, SquareState } from "./types";

type Spec = [row: number, col: number, kind: SquareKind, text: string, state: SquareState,
  extra?: Partial<Square>];

const RANGES = ["0-1", "2-3", "4+"];
const TEAMS = ["NBA", "KVL"];
const LABELS: Record<string, string> = {
  "0-1": "0–1", "2-3": "2–3", "4+": "4+", NBA: "Northbridge", KVL: "Kestrel", yes: "Yes", no: "No",
  foul: "Foul", offside: "Offside", advantage: "Advantage played", no_call: "No call",
  corner: "Corner", goal_kick: "Goal kick", throw_in: "Throw-in",
};

const SPECS: Spec[] = [
  [0, 0, "live", "What did the referee just give?", "wildcard",
    { answer_type: "choice", options: ["foul", "offside", "advantage", "no_call"],
      source_event_ids: ["e000221", "e000222"] }],
  [0, 1, "deadline", "How many yellow cards by 15'?", "correct", { deadline_s: 900, masks: ["cards"] }],
  [0, 2, "first", "Who commits the first foul?", "correct", { answer_type: "team", masks: ["fouls"] }],
  [0, 3, "deadline", "How many corners by 20'?", "wrong", { deadline_s: 1200, masks: ["corners"] }],
  [0, 4, "live", "", "empty_blank"],
  [1, 0, "first", "Who wins the first corner?", "correct", { answer_type: "team", masks: ["corners"] }],
  [1, 1, "deadline", "Which team has more shots by 30'?", "missed",
    { deadline_s: 1800, answer_type: "team", masks: ["shots"] }],
  [1, 2, "first", "Who takes the first shot?", "too_early", { answer_type: "team", masks: ["shots"] }],
  [1, 3, "deadline", "Will there be a goal by 40'?", "open",
    { deadline_s: 2400, answer_type: "yesno", options: ["yes", "no"], masks: ["goals"] }],
  [1, 4, "first", "Who is first caught offside?", "waiting", { answer_type: "team", masks: ["offsides"] }],
  [2, 0, "deadline", "How many offsides by 45:00?", "correct", { deadline_s: 2700, masks: ["offsides"] }],
  [2, 1, "first", "Who is booked first?", "waiting", { answer_type: "team", masks: ["cards"] }],
  [2, 2, "live", "", "empty_blank"],
  [2, 3, "deadline", "Who has more possession at 55'?", "waiting",
    { deadline_s: 3300, answer_type: "team", masks: ["possession"] }],
  [2, 4, "first", "Who has the first shot on target?", "waiting", { answer_type: "team", masks: ["shots"] }],
  [3, 0, "first", "Who is subbed off first?", "void", { answer_type: "team", masks: ["subs"] }],
  [3, 1, "deadline", "How many substitutions by 60'?", "waiting", { deadline_s: 3600, masks: ["subs"] }],
  [3, 2, "first", "Who scores first?", "waiting", { answer_type: "team", masks: ["goals"] }],
  [3, 3, "deadline", "How many fouls by Kestrel by 70'?", "waiting", { deadline_s: 4200, masks: ["fouls"] }],
  [3, 4, "deadline", "How many yellow cards by 80'?", "waiting", { deadline_s: 4800, masks: ["cards"] }],
  [4, 0, "live", "How does play restart?", "wildcard",
    { answer_type: "choice", options: ["corner", "goal_kick", "throw_in"], source_event_ids: ["e000705"] }],
  [4, 1, "deadline", "How many fouls by Northbridge by 50'?", "waiting",
    { deadline_s: 3000, masks: ["fouls"] }],
  [4, 2, "deadline", "How many corners by 90:00?", "waiting", { deadline_s: 5400, masks: ["corners"] }],
  [4, 3, "deadline", "Will there be a goal by 85'?", "waiting",
    { deadline_s: 5100, answer_type: "yesno", options: ["yes", "no"], masks: ["goals"] }],
  [4, 4, "live", "", "empty_blank"],
];

function square([row, col, kind, text, state, extra = {}]: Spec): Square {
  const blank = state === "empty_blank";
  const answerType = extra.answer_type ?? "number";
  const options = extra.options ?? (answerType === "number" ? RANGES : answerType === "team" ? TEAMS : []);
  return {
    id: blank ? `blank_${row}${col}` : `sq_${String(row * 5 + col).padStart(2, "0")}`,
    kind,
    text: text ? { en: text } : {},
    answer_type: answerType,
    options,
    option_labels: options.length ? { en: options.map((o) => LABELS[o] ?? o) } : {},
    deadline_s: null,
    trigger: null,
    resolver: blank ? "" : "mock",
    masks: [],
    cell: { row, col },
    state,
    answer: null,
    result: null,
    source_event_ids: [],
    closes_at: state === "open" ? Date.now() + 14_000 : null,
    ...extra,
  };
}

export const mockBoard: Board = {
  squares: SPECS.map(square),
  scored_lines: ["col:0"],
  points: 1_342,
  correct: 6,
  bingos: 1,
};
