// Leaderboard (spec 3): the top five plus your row, against simulated fans in your mode.

import { t } from "../i18n";
import type { LeaderboardRow, Mode } from "../protocol";

export function Leaderboard({ rows, mode }: { rows: LeaderboardRow[]; mode: Mode }) {
  return (
    <section className="leaderboard" aria-labelledby="leaderboard-title">
      <div className="card-header">
        <h2 id="leaderboard-title">{t("leaderboard.title")}</h2>
        <span className="muted small">{t("leaderboard.mode", { mode: t(`top.mode.${mode}`) })}</span>
      </div>
      {rows.length === 0 ? (
        <p className="muted">{t("leaderboard.empty")}</p>
      ) : (
        <table className="stat-table board-table">
          <thead>
            <tr>
              <th scope="col">{t("leaderboard.rank")}</th>
              <th scope="col">{t("leaderboard.handle")}</th>
              <th scope="col">{t("leaderboard.points")}</th>
              <th scope="col">{t("leaderboard.correct")}</th>
              <th scope="col">{t("leaderboard.time")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.rank}-${row.handle}`} className={row.you ? "you" : undefined}>
                <td>{row.rank}</td>
                <th scope="row">
                  {row.handle}{" "}
                  {row.you && row.handle !== "You" && <span className="muted">{t("leaderboard.you")}</span>}
                </th>
                <td>{row.points.toLocaleString("en")}</td>
                <td>{row.correct}</td>
                <td>{row.avg_answer_s === null ? "–" : `${row.avg_answer_s.toFixed(1)} s`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
