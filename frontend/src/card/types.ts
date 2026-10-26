// The card, shaped like the square record in spec 4.2 and the board.update message in 9.4,
// so phase 4's real board can replace mock.ts without touching the component.

export type SquareKind = "deadline" | "first" | "live";
export type AnswerType = "player" | "team" | "number" | "choice" | "yesno";

/** Spec 4.3. "locked" isn't stored per square: a square is locked when a scored line holds it. */
export type SquareState =
  | "waiting"
  | "open"
  | "correct"
  | "wrong"
  | "too_early"
  | "missed"
  | "void"
  | "empty_blank"
  | "wildcard";

export interface Cell {
  row: number; // 0-4
  col: number; // 0-4
}

export interface Square {
  id: string;
  kind: SquareKind;
  text: Record<string, string>; // per language, 60 characters at most
  answer_type: AnswerType;
  options: string[];
  deadline_s: number | null; // deadline squares: the match second the count freezes at
  trigger: Record<string, string> | null; // first-to-happen squares: an event filter
  resolver: string;
  masks: string[];
  cell: Cell;
  state: SquareState;
  answer: { value: string; wall_ms: number; t: number } | null;
  result: { status: SquareState; points: number; explanation: string; evidence_event_ids: string[] } | null;
  source_event_ids: string[]; // live squares
  closes_at: number | null; // open window: wall-clock ms (square.window_open in spec 9.4)
}

/** "row:0".."row:4", "col:0".."col:4", "diag:0" (top-left to bottom-right), "diag:1". */
export type LineId = string;

export interface Board {
  squares: Square[];
  scored_lines: LineId[];
  points: number;
  correct: number;
  bingos: number;
}

export function linesOf(cell: Cell): LineId[] {
  const lines = [`row:${cell.row}`, `col:${cell.col}`];
  if (cell.row === cell.col) lines.push("diag:0");
  if (cell.row + cell.col === 4) lines.push("diag:1");
  return lines;
}

export function isLocked(square: Square, board: Board): boolean {
  return linesOf(square.cell).some((line) => board.scored_lines.includes(line));
}

/** "at 70'", or "at 45:00" / "at 90:00" for the end-of-half readings (spec 4.1, 4.4). */
export function deadlineLabel(deadlineS: number): string {
  const minute = Math.floor(deadlineS / 60);
  return deadlineS % 2700 === 0 ? `${minute}:00` : `${minute}'`;
}
