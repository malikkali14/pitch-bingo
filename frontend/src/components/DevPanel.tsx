// Dev panel (spec 3): pause, jump to a minute, the narrator failure switch, and agent health.
// For demo recording only; DEV_PANEL=false on the server turns the commands off.

import { useState } from "react";
import { t } from "../i18n";
import type { HealthMessage } from "../protocol";

interface Props {
  health: HealthMessage | null;
  paused: boolean;
  narratorDown: boolean;
  onPause(on: boolean): void;
  onJump(minute: number): void;
  onNarratorDown(on: boolean): void;
}

export function DevPanel({ health, paused, narratorDown, onPause, onJump, onNarratorDown }: Props) {
  const [minute, setMinute] = useState("33");
  return (
    <section className="dev-panel" aria-labelledby="dev-title">
      <h2 id="dev-title">{t("dev.title")}</h2>
      <div className="dev-controls">
        <button type="button" className="ghost" aria-pressed={paused} onClick={() => onPause(!paused)}>
          {paused ? t("dev.resume") : t("dev.pause")}
        </button>
        <form onSubmit={(e) => {
          e.preventDefault();
          const m = Number(minute);
          if (Number.isFinite(m) && m >= 0) onJump(m);
        }}>
          <label>
            {t("dev.jump")}{" "}
            <input type="number" min={0} max={130} value={minute} onChange={(e) => setMinute(e.target.value)} />
          </label>{" "}
          <button type="submit" className="ghost">{t("dev.go")}</button>{" "}
          <span className="muted small">{t("dev.jump_note")}</span>
        </form>
        <label className="choice">
          <input type="checkbox" checked={narratorDown} onChange={(e) => onNarratorDown(e.target.checked)} />{" "}
          {t("dev.narrator")}
        </label>
      </div>
      {health && !health.online && <p className="muted small">{t("dev.offline")}</p>}
      {health && (
        <>
          <p className="small">{t("dev.rates", { calls: health.llm_calls_per_minute, events: health.events_per_minute })}</p>
          <table className="stat-table dev-table">
            <thead>
              <tr>
                <th scope="col">{t("dev.agent")}</th>
                <th scope="col">{t("dev.breaker")}</th>
                <th scope="col">{t("dev.per_minute")}</th>
                <th scope="col">{t("dev.latency")}</th>
                <th scope="col">{t("dev.ai")}</th>
                <th scope="col">{t("dev.verifier")}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(health.agents).map(([name, a]) => (
                <tr key={name}>
                  <th scope="row">{name}</th>
                  <td className={`breaker ${a.breaker}`}>{t(`dev.breaker.${a.breaker}`)}</td>
                  <td>{a.per_minute}</td>
                  <td>{a.latency_ms === null ? "–" : `${a.latency_ms} ms`}</td>
                  <td>{a.ai} / {a.fallbacks}</td>
                  <td>{a.verifier_failures}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
