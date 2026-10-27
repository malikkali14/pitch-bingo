// Full-time screen (spec 3): final score, the three biggest moments, your card and rank.
// The personalized recap arrives with the recap agent in phase 6.

import { useEffect, useRef } from "react";
import type { Board } from "../card/types";
import { t } from "../i18n";
import type { LeaderboardRow, Mode, RecapMessage } from "../protocol";
import type { Roster } from "../roster";
import type { Moment } from "../state/match";

interface Props {
  roster: Roster;
  score: Record<string, number> | undefined;
  board: Board;
  moments: Moment[];
  leaderboard: LeaderboardRow[];
  total: number;
  mode: Mode;
  recap?: RecapMessage;
  onClose(): void;
}

export function cardSummary(board: Board) {
  const count = (states: string[]) => board.squares.filter((s) => states.includes(s.state)).length;
  return {
    correct: board.correct,
    wrong: count(["wrong", "too_early"]),
    missed: count(["missed"]),
    lines: board.scored_lines.length,
    points: board.points,
  };
}

export function FullTime({ roster, score, board, moments, leaderboard, total, mode, recap, onClose }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => panel.current?.focus(), []);
  const you = leaderboard.find((r) => r.you);
  const summary = cardSummary(board);
  return (
    <div className="fulltime-backdrop">
      <div className="fulltime" role="dialog" aria-modal="true" aria-labelledby="fulltime-title"
        tabIndex={-1} ref={panel} onKeyDown={(e) => e.key === "Escape" && onClose()}>
        <h2 id="fulltime-title">{t("fulltime.title")}</h2>
        <p className="final-score">
          {roster.home.name} {score?.[roster.home.id] ?? 0} – {score?.[roster.away.id] ?? 0} {roster.away.name}
        </p>
        {recap && (
          <section className="recap" aria-label={t("fulltime.recap")}>
            <h3>
              {recap.content.headline} {recap.ai && <span className="ai">{t("feed.ai")}</span>}
            </h3>
            {[...recap.content.paragraphs, recap.content.club_paragraph, recap.content.player_paragraph]
              .filter(Boolean).map((p, i) => <p key={i}>{p}</p>)}
            <h4>{t("fulltime.talking_points")}</h4>
            <ul>{recap.content.talking_points.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </section>
        )}
        <h3>{t("fulltime.moments")}</h3>
        <ol className="moments">
          {moments.map((m) => (
            <li key={m.event.event_id}>
              <span className="minute">{m.event.clock.split(":")[0]}'</span> {m.text}
            </li>
          ))}
        </ol>
        <h3>{t("fulltime.card")}</h3>
        <p>{t("fulltime.summary", { ...summary, points: summary.points.toLocaleString("en") })}</p>
        {you && <p>{t("fulltime.rank", { rank: you.rank, total, mode: t(`top.mode.${mode}`) })}</p>}
        <p className="muted small">{t("fulltime.merch")}</p>
        <button type="button" className="primary" onClick={onClose}>{t("fulltime.keep")}</button>
      </div>
    </div>
  );
}
