// Metrics panel (spec 3): normal mode basics, advanced mode adds xG, passing and pressure.

import { useState } from "react";
import { t } from "../i18n";
import type { StatsMessage } from "../protocol";
import type { Roster } from "../roster";
import type { XgPoint } from "../state/match";
import type { Mode } from "./TopBar";

interface Props {
  roster: Roster;
  stats: StatsMessage | null;
  xg: XgPoint[];
  mode: Mode;
  definition?: { term: string; text: string; ai: boolean } | null;
  onDefine?(term: string | null): void;
}

const dash = "–";
const num = (v: number | null | undefined, digits = 0, unit = "") =>
  v === null || v === undefined ? dash : `${v.toFixed(digits)}${unit}`;
/** A stat an open square depends on arrives as null: show "Hidden" (spec 3, 4.9). */
const shown = (v: number | null | undefined, text: (v: number) => string = String) =>
  v === null || v === undefined ? t("metrics.hidden") : text(v);

/** Normal mode: tap a stat's name for a one-line explanation (spec 5.1). */
function Term({ term, label, onDefine }: { term: string; label: string; onDefine?(term: string): void }) {
  if (!onDefine) return <>{label}</>;
  return (
    <button type="button" className="term" onClick={() => onDefine(term)}
      aria-label={t("metrics.define", { stat: label })}>{label}</button>
  );
}

export function Metrics({ roster, stats, xg, mode, definition, onDefine }: Props) {
  const define = mode === "normal" ? onDefine : undefined;
  if (!stats) {
    return (
      <section className="metrics" aria-labelledby="metrics-title">
        <h2 id="metrics-title">{t("metrics.title")}</h2>
        <p className="muted">{t("metrics.waiting")}</p>
      </section>
    );
  }
  const home = stats.clubs[roster.home.id];
  const away = stats.clubs[roster.away.id];
  const pressure = stats.patterns.pressure;
  const masked = new Set(stats.masked ?? []);
  const shots = (c: typeof home) => shown(c.shots, (n) => `${n} (${c.shots_on_target})`);
  const cards = (c: typeof home) => shown(c.yellow_cards, (n) => `${n} / ${c.red_cards}`);
  const tilt = (id: string) => masked.has("possession")
    ? t("metrics.hidden") : num(pressure[id]?.field_tilt, 0, "%");
  const rows: [string, string, string, string][] = [
    [t("metrics.shots"), shots(home), shots(away), "shots"],
    [t("metrics.corners"), shown(home.corners), shown(away.corners), "corners"],
    [t("metrics.fouls"), shown(home.fouls), shown(away.fouls), "fouls"],
    [t("metrics.cards"), cards(home), cards(away), "cards"],
  ];
  if (mode === "advanced") {
    rows.push(
      [t("metrics.xg"), shown(home.xg, (n) => n.toFixed(2)), shown(away.xg, (n) => n.toFixed(2)), "xg"],
      [t("metrics.pass_accuracy"), num(home.pass_accuracy, 0, "%"), num(away.pass_accuracy, 0, "%"),
        "pass_accuracy"],
      [t("metrics.ppda"), num(pressure[roster.home.id]?.ppda, 1), num(pressure[roster.away.id]?.ppda, 1),
        "ppda"],
      [t("metrics.field_tilt"), tilt(roster.home.id), tilt(roster.away.id), "field_tilt"],
    );
  }
  return (
    <section className="metrics" aria-labelledby="metrics-title">
      <h2 id="metrics-title">{t("metrics.title")}</h2>
      <SplitBar label={t("metrics.possession")} home={home.possession} homeName={roster.home.short_name}
        awayName={roster.away.short_name} />
      <table className="stat-table">
        <thead>
          <tr>
            <th scope="col"><span className="visually-hidden">Stat</span></th>
            <th scope="col"><span className="swatch home" aria-hidden="true" /> {roster.home.short_name}</th>
            <th scope="col">{roster.away.short_name} <span className="swatch away" aria-hidden="true" /></th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, h, a, term]) => (
            <tr key={label}>
              <th scope="row"><Term term={term} label={label} onDefine={define} /></th>
              <td>{h}</td>
              <td>{a}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {define && (
        <p className="terms small">
          {t("metrics.explain")}{" "}
          {(["possession", "momentum", "chaos"] as const).map((term) => (
            <Term key={term} term={term} label={t(`metrics.${term}`)} onDefine={define} />
          ))}
        </p>
      )}
      {definition && (
        <div className="definition" role="status">
          <p>
            <strong>{definition.term.replace(/_/g, " ")}:</strong>{" "}
            {definition.text || "…"} {definition.ai && <span className="ai">{t("feed.ai")}</span>}
          </p>
          <button type="button" className="ghost" onClick={() => onDefine?.(null)}>{t("card.close")}</button>
        </div>
      )}
      <Momentum value={stats.patterns.momentum.value} roster={roster} />
      <ChaosMeter value={stats.patterns.chaos.value} inControl={roster.team(stats.patterns.chaos.in_control)?.short_name} />
      {mode === "advanced" && (
        <>
          {!masked.has("shots") && <XgTimeline points={xg} now={stats.t} roster={roster} />}
          <p className="stat-line">
            <span className="stat-label">{t("metrics.tempo")}</span> {stats.patterns.rhythm.tempo ?? dash}
          </p>
          <TopPerformer stats={stats} roster={roster} />
        </>
      )}
    </section>
  );
}

export function SplitBar({ label, home, homeName, awayName }: { label: string; home: number | null; homeName: string; awayName: string }) {
  if (home === null) {
    return (
      <div className="split">
        <div className="split-labels">
          <span>{homeName}</span>
          <span className="stat-label">{label}: {t("metrics.hidden")}</span>
          <span>{awayName}</span>
        </div>
        <div className="split-bar hidden" aria-hidden="true" />
      </div>
    );
  }
  const away = 100 - home;
  return (
    <div className="split">
      <div className="split-labels">
        <span>{homeName} {home.toFixed(0)}%</span>
        <span className="stat-label">{label}</span>
        <span>{away.toFixed(0)}% {awayName}</span>
      </div>
      <div className="split-bar" role="img" aria-label={`${label}: ${homeName} ${home.toFixed(0)}%, ${awayName} ${away.toFixed(0)}%`}>
        <span className="fill home" style={{ width: `${home}%` }} />
        <span className="fill away" style={{ width: `${away}%` }} />
      </div>
    </div>
  );
}

export function Momentum({ value, roster }: { value: number; roster: Roster }) {
  const side = value > 0 ? roster.home : value < 0 ? roster.away : null;
  const size = Math.min(100, Math.abs(value)) / 2;
  const text = side ? `${side.short_name} +${Math.abs(value).toFixed(0)}` : dash;
  return (
    <div className="momentum">
      <div className="split-labels">
        <span>{roster.home.short_name}</span>
        <span className="stat-label">{t("metrics.momentum")}: {text}</span>
        <span>{roster.away.short_name}</span>
      </div>
      <div className="momentum-bar" role="img" aria-label={`${t("metrics.momentum")}: ${text}`}>
        <span className="midline" />
        {side && (
          <span className={`fill ${value > 0 ? "home" : "away"}`}
            style={value > 0 ? { right: "50%", width: `${size}%` } : { left: "50%", width: `${size}%` }} />
        )}
      </div>
    </div>
  );
}

export function ChaosMeter({ value, inControl }: { value: number | null; inControl?: string }) {
  const label = value === null ? dash : value.toFixed(0);
  return (
    <div className="chaos">
      <div className="split-labels">
        <span>{t("metrics.calm")}</span>
        <span className="stat-label">{t("metrics.chaos")}: {label}</span>
        <span>{t("metrics.chaotic")}</span>
      </div>
      <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={value ?? undefined} aria-label={t("metrics.chaos")}>
        {value !== null && <span className="fill" style={{ width: `${value}%` }} />}
      </div>
      {inControl && <p className="muted small">{t("metrics.in_control", { team: inControl })}</p>}
    </div>
  );
}

function XgTimeline({ points, now, roster }: { points: XgPoint[]; now: number; roster: Roster }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length === 0) return null;
  const w = 280;
  const h = 70;
  const end = Math.max(now, 60);
  const top = Math.max(0.5, ...points.map((p) => Math.max(p.home, p.away)));
  const sx = (t: number) => (t / end) * w;
  const sy = (v: number) => h - 4 - (v / top) * (h - 8);
  // Step lines: xG only changes at shots.
  const path = (key: "home" | "away") => {
    let d = `M0,${sy(0)}`;
    for (const p of points) d += ` H${sx(p.t)} V${sy(p[key])}`;
    return `${d} H${sx(now)}`;
  };
  const last = points[points.length - 1];
  const at = hover === null ? null : [...points].reverse().find((p) => p.t <= hover) ?? null;
  return (
    <figure className="xg-timeline">
      <figcaption className="stat-label">{t("metrics.xg_timeline")}</figcaption>
      <svg viewBox={`0 0 ${w} ${h}`} role="img"
        aria-label={`${t("metrics.xg_timeline")}: ${roster.home.short_name} ${last.home.toFixed(2)}, ${roster.away.short_name} ${last.away.toFixed(2)}`}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          setHover(((e.clientX - box.left) / box.width) * end);
        }}
        onMouseLeave={() => setHover(null)}>
        <line className="baseline" x1={0} y1={sy(0)} x2={w} y2={sy(0)} />
        <path className="series home" d={path("home")} />
        <path className="series away" d={path("away")} />
        {hover !== null && <line className="crosshair" x1={sx(hover)} y1={0} x2={sx(hover)} y2={h} />}
      </svg>
      <p className="legend small">
        <span><span className="swatch home" aria-hidden="true" /> {roster.home.short_name} {(at ?? last).home.toFixed(2)}</span>
        <span><span className="swatch away" aria-hidden="true" /> {roster.away.short_name} {(at ?? last).away.toFixed(2)}</span>
      </p>
    </figure>
  );
}

/** Spec 3 doesn't define "top performer"; for now it's the player with the most touches. */
export function topPerformer(stats: StatsMessage): string | null {
  let best: string | null = null;
  let most = -1;
  for (const [id, p] of Object.entries(stats.players)) {
    if (p.touches > most) {
      best = id;
      most = p.touches;
    }
  }
  return best;
}

function TopPerformer({ stats, roster }: { stats: StatsMessage; roster: Roster }) {
  const id = topPerformer(stats);
  const player = id ? roster.players.get(id) : undefined;
  if (!id || !player) return null;
  const p = stats.players[id];
  return (
    <p className="stat-line">
      <span className="stat-label">{t("metrics.top_performer")}</span>{" "}
      {t("metrics.top_performer_line", {
        player: player.surname,
        team: player.team.short_name,
        touches: p.touches,
        passes: `${p.passes_completed}/${p.passes}`,
      })}
    </p>
  );
}
