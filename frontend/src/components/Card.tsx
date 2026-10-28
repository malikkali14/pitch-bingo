// The 5x5 bingo card (spec 3, bingo card): states, answering and moving blanks.
// Tap or press Enter on a square to answer it. Blanks and wildcards move by dragging, or by
// picking one up (Enter) and then choosing a waiting square (Enter again); Escape cancels.

import { useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import { announcedOpen, canMove, canPickUp } from "../card/rules";
import { deadlineLabel, isLocked, type Board, type Cell, type Square } from "../card/types";
import { useNow } from "../hooks";
import { getLanguage, t } from "../i18n";
import type { StrategyAdviceMessage } from "../protocol";
import type { Roster } from "../roster";
import { AnswerPopover } from "./AnswerPopover";

const KIND_ICON = { deadline: "⏱", first: "⚡", live: "★" } as const;
const STATE_ICON: Record<string, string> = {
  waiting: "…",
  open: "◔",
  correct: "✓",
  wrong: "✗",
  too_early: "✗",
  missed: "–",
  void: "○",
  empty_blank: "",
  wildcard: "★",
};

interface Props {
  board: Board;
  roster?: Roster;
  language?: string;
  pending?: Record<string, string>;
  answers?: Record<string, string | null>;
  advice?: StrategyAdviceMessage | null;
  selected?: string | null;
  onSelect?(squareId: string | null): void;
  onAnswer?(squareId: string, value: string): void;
  onMove?(from: Cell, to: Cell): void;
}

const same = (a: Cell | null | undefined, b: Cell) => !!a && a.row === b.row && a.col === b.col;

export function Card(props: Props) {
  const { board, roster, language = "en", pending = {}, answers = {}, advice, selected = null } = props;
  const now = useNow(250);
  const [focus, setFocus] = useState(0);
  const [moving, setMoving] = useState<Cell | null>(null);
  const [dragging, setDragging] = useState<Cell | null>(null);
  const [blocked, setBlocked] = useState(false);
  const cells = useRef<(HTMLDivElement | null)[]>([]);
  const byCell = new Map(board.squares.map((s) => [s.cell.row * 5 + s.cell.col, s]));
  const windowOpen = announcedOpen(board);
  const from = dragging ?? moving;
  const selectedSquare = board.squares.find((s) => s.id === selected) ?? null;

  const activate = (square: Square) => {
    setBlocked(false);
    if (moving) {
      if (canMove(board, moving, square.cell)) props.onMove?.(moving, square.cell);
      setMoving(null);
      return;
    }
    if (canPickUp(square, board) && props.onMove) {
      if (windowOpen) setBlocked(true);
      else setMoving(square.cell);
      return;
    }
    if (square.state !== "empty_blank") props.onSelect?.(square.id === selected ? null : square.id);
  };

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      setMoving(null);
      props.onSelect?.(null);
      return;
    }
    const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -5, ArrowDown: 5 };
    const index = cells.current.findIndex((el) => el?.contains(e.target as Node));
    const current = index === -1 ? focus : index;
    if (e.key === "Enter" && (e.target as HTMLElement).getAttribute("role") === "gridcell") {
      const square = byCell.get(current);
      if (square) activate(square);
      e.preventDefault();
      return;
    }
    if (!(e.key in step)) return;
    e.preventDefault();
    const next = current + step[e.key];
    const sameRow = e.key === "ArrowLeft" || e.key === "ArrowRight";
    if (next < 0 || next > 24 || (sameRow && Math.floor(next / 5) !== Math.floor(current / 5))) return;
    setFocus(next);
    cells.current[next]?.focus();
  };

  const drag = (square: Square) => ({
    draggable: !!props.onMove && canPickUp(square, board) && !windowOpen,
    onDragStart: (e: DragEvent) => {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", `${square.cell.row},${square.cell.col}`);
      setDragging(square.cell);
    },
    onDragEnd: () => setDragging(null),
    onDragOver: (e: DragEvent) => {
      if (dragging && canMove(board, dragging, square.cell)) e.preventDefault();
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      if (dragging && canMove(board, dragging, square.cell)) props.onMove?.(dragging, square.cell);
      setDragging(null);
    },
  });

  return (
    <section className="card" aria-labelledby="card-title">
      <div className="card-header">
        <h2 id="card-title">{t("card.title")}</h2>
        <dl className="card-totals">
          <div><dt>{t("card.points")}</dt><dd>{board.points.toLocaleString(getLanguage())}</dd></div>
          <div><dt>{t("card.correct")}</dt><dd>{board.correct}</dd></div>
          <div><dt>{t("card.lines")}</dt><dd>{board.scored_lines.length}</dd></div>
          <div><dt>{t("card.bingos")}</dt><dd>{board.bingos}</dd></div>
        </dl>
      </div>
      <p className="hint">{t("card.hint")}</p>
      {moving && <p className="move-hint" role="status">{t("card.move_pick")}</p>}
      {blocked && <p className="move-hint" role="status">{t("card.move_blocked")}</p>}
      <div className="grid keep-light" role="grid" aria-labelledby="card-title" onKeyDown={onKey}>
        {[0, 1, 2, 3, 4].map((row) => (
          <div key={row} role="row" className="grid-row">
            {[0, 1, 2, 3, 4].map((col) => {
              const index = row * 5 + col;
              const square = byCell.get(index);
              const cell = { row, col };
              const target = !!from && !same(from, cell) && canMove(board, from, cell);
              const cls = ["cell-wrap", target && "drop-target", same(from, cell) && "moving",
                advice?.moves.some((m) => same(m.from_cell, cell)) && "advice-from",
                advice?.moves.some((m) => same(m.to_cell, cell)) && "advice-to",
                square && square.id === selected && "selected"].filter(Boolean).join(" ");
              return (
                <div key={col} role="gridcell" tabIndex={index === focus ? 0 : -1}
                  ref={(el) => (cells.current[index] = el)} onFocus={() => setFocus(index)}
                  className={cls} onClick={() => square && activate(square)}
                  aria-selected={square?.id === selected}
                  aria-label={square ? squareLabel(square, isLocked(square, board), language, now) : undefined}
                  {...(square ? drag(square) : {})}>
                  {square && (
                    <SquareView square={square} locked={isLocked(square, board)} language={language}
                      now={now} pending={pending[square.id] !== undefined} />
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      {selectedSquare && roster && (
        <AnswerPopover square={selectedSquare} roster={roster} language={language}
          pending={pending[selectedSquare.id]} correctAnswer={answers[selectedSquare.id]}
          onAnswer={(value) => props.onAnswer?.(selectedSquare.id, value)}
          onClose={() => props.onSelect?.(null)} />
      )}
    </section>
  );
}

export function squareLabel(square: Square, locked: boolean, language: string, now: number): string {
  if (square.state === "empty_blank") return t("card.blank");
  const parts = [t(`card.kind.${square.kind}`), square.text[language] ?? square.text.en ?? ""];
  if (square.kind === "deadline" && square.deadline_s !== null) {
    parts.push(t("card.at", { minute: deadlineLabel(square.deadline_s) }));
  }
  parts.push(t(`card.state.${square.state}`));
  if (square.state === "open") parts.push(t("card.seconds_left", { seconds: secondsLeft(square, now) }));
  if (locked) parts.push(t("card.state.locked"));
  return parts.filter(Boolean).join(". ");
}

function secondsLeft(square: Square, now: number): number {
  return square.closes_at === null ? 0 : Math.max(0, Math.ceil((square.closes_at - now) / 1000));
}

interface SquareProps {
  square: Square;
  locked: boolean;
  language: string;
  now: number;
  pending: boolean;
}

function SquareView({ square, locked, language, now, pending }: SquareProps) {
  const label = squareLabel(square, locked, language, now);
  const cls = `square ${square.state}${locked ? " locked" : ""}`;
  if (square.state === "empty_blank") {
    return <div className={cls} title={label} />;
  }
  const points = square.result?.points ?? 0;
  return (
    <div className={cls} title={label}>
      <div className="square-top" aria-hidden="true">
        <span className="kind">{KIND_ICON[square.kind]}</span>
        {square.kind === "deadline" && square.deadline_s !== null && (
          <span className="deadline">{deadlineLabel(square.deadline_s)}</span>
        )}
        <span className="state-icon">
          {square.state === "open" ? <Countdown seconds={secondsLeft(square, now)} /> : STATE_ICON[square.state]}
        </span>
      </div>
      <p className="question" aria-hidden="true">{square.text[language] ?? square.text.en}</p>
      <p className="state-label" aria-hidden="true">
        {locked ? t("card.state.locked") : pending ? "…" : t(`card.state.${square.state}`)}
        {points > 0 && <span className="points"> {t("card.points_won", { points })}</span>}
      </p>
    </div>
  );
}

function Countdown({ seconds }: { seconds: number }) {
  const r = 7;
  const c = 2 * Math.PI * r;
  return (
    <svg className="countdown" viewBox="0 0 18 18" width="18" height="18">
      <circle className="track" cx="9" cy="9" r={r} />
      <circle className="ring" cx="9" cy="9" r={r} strokeDasharray={c}
        strokeDashoffset={c * (1 - seconds / 20)} transform="rotate(-90 9 9)" />
      <text x="9" y="9" textAnchor="middle" dominantBaseline="central">{seconds}</text>
    </svg>
  );
}
