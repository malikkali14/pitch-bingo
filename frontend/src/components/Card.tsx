// The 5x5 bingo card (spec 3, bingo card). Layout and states only: answering, moving blanks
// and the strategist strip come with the game API in phase 4.

import { useRef, useState, type KeyboardEvent } from "react";
import { deadlineLabel, isLocked, type Board, type Square } from "../card/types";
import { useNow } from "../hooks";
import { t } from "../i18n";

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
  language?: string;
  note?: string;
}

export function Card({ board, language = "en", note }: Props) {
  const now = useNow(250);
  const [focus, setFocus] = useState(0);
  const cells = useRef<(HTMLDivElement | null)[]>([]);
  const byCell = new Map(board.squares.map((s) => [s.cell.row * 5 + s.cell.col, s]));

  const move = (e: KeyboardEvent) => {
    const step: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -5, ArrowDown: 5 };
    if (!(e.key in step)) return;
    e.preventDefault();
    const from = cells.current.findIndex((el) => el?.contains(e.target as Node));
    const current = from === -1 ? focus : from;
    const next = current + step[e.key];
    const sameRow = e.key === "ArrowLeft" || e.key === "ArrowRight";
    if (next < 0 || next > 24 || (sameRow && Math.floor(next / 5) !== Math.floor(current / 5))) return;
    setFocus(next);
    cells.current[next]?.focus();
  };

  return (
    <section className="card" aria-labelledby="card-title">
      <div className="card-header">
        <h2 id="card-title">{t("card.title")}</h2>
        <dl className="card-totals">
          <div><dt>{t("card.points")}</dt><dd>{board.points.toLocaleString("en")}</dd></div>
          <div><dt>{t("card.correct")}</dt><dd>{board.correct}</dd></div>
          <div><dt>{t("card.lines")}</dt><dd>{board.scored_lines.length}</dd></div>
          <div><dt>{t("card.bingos")}</dt><dd>{board.bingos}</dd></div>
        </dl>
      </div>
      {note && <p className="muted small">{note}</p>}
      <div className="grid" role="grid" aria-labelledby="card-title" onKeyDown={move}>
        {[0, 1, 2, 3, 4].map((row) => (
          <div key={row} role="row" className="grid-row">
            {[0, 1, 2, 3, 4].map((col) => {
              const index = row * 5 + col;
              const square = byCell.get(index);
              return (
                <div key={col} role="gridcell" tabIndex={index === focus ? 0 : -1}
                  ref={(el) => (cells.current[index] = el)} onFocus={() => setFocus(index)}
                  className="cell-wrap">
                  {square && (
                    <SquareView square={square} locked={isLocked(square, board)} language={language} now={now} />
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
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

function SquareView({ square, locked, language, now }: { square: Square; locked: boolean; language: string; now: number }) {
  const label = squareLabel(square, locked, language, now);
  const cls = `square ${square.state}${locked ? " locked" : ""}`;
  if (square.state === "empty_blank") {
    return <div className={cls} aria-label={label} title={label} />;
  }
  return (
    <div className={cls} aria-label={label} title={label}>
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
        {locked ? t("card.state.locked") : t(`card.state.${square.state}`)}
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
