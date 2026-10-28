import { clockAt, type ClockAnchor } from "../clock";
import { useFrameTime } from "../hooks";
import { t } from "../i18n";
import { SPEEDS, type Mode, type Speed } from "../protocol";
import type { Roster } from "../roster";
import type { FrameStore } from "../state/frames";

export type { Mode };

interface Props {
  roster: Roster;
  score: Record<string, number> | undefined;
  anchor: ClockAnchor | null;
  fullTime: boolean;
  frames: FrameStore;
  speed: Speed;
  onSpeed(speed: Speed): void;
  mode: Mode;
  onMode(mode: Mode): void;
  devOpen?: boolean;
  onDev?(): void;
  /** Surname of the fan's focus player, shown as a profile chip. */
  following?: string;
  dark?: boolean;
  onTheme?(): void;
  onHelp?(): void;
  language?: string;
}

export function halfLabel(anchor: ClockAnchor | null, fullTime: boolean): string {
  if (fullTime) return t("top.half.ft");
  if (!anchor) return t("top.half.pre");
  return t(`top.half.${anchor.period}`);
}

function MatchClock({ anchor, fullTime, frames }: Pick<Props, "anchor" | "fullTime" | "frames">) {
  const now = useFrameTime(frames);
  const time = fullTime && anchor ? anchor.t : now;
  return (
    <span className="clock" role="timer">
      {clockAt(anchor, time)}
    </span>
  );
}

export function TopBar(props: Props) {
  const { roster, score, anchor, fullTime, frames, speed, onSpeed, mode, onMode, devOpen, onDev, following, language, dark, onTheme, onHelp } = props;
  const home = score?.[roster.home.id] ?? 0;
  const away = score?.[roster.away.id] ?? 0;
  return (
    <header className="topbar">
      <div className="scoreboard" role="group" aria-label={t("top.scoreboard")}>
        <span className="team home">
          <span className="swatch home" aria-hidden="true" />
          {roster.home.name}
        </span>
        <span className="score" aria-live="polite">
          <span className="visually-hidden">
            {roster.home.short_name} {home}, {roster.away.short_name} {away}
          </span>
          <span aria-hidden="true">
            {home} – {away}
          </span>
        </span>
        <span className="team away">
          {roster.away.name}
          <span className="swatch away" aria-hidden="true" />
        </span>
        <MatchClock anchor={anchor} fullTime={fullTime} frames={frames} />
        <span className="half">{halfLabel(anchor, fullTime)}</span>
      </div>
      <div className="controls">
        <p className="chip" aria-label={t("top.profile")}>
          {following && <span>{t("top.following", { player: following })} · </span>}
          {t(`top.mode.${mode}`)}{language ? ` · ${language.toUpperCase()}` : ""}
        </p>
        <div className="segmented" role="group" aria-label={t("top.speed")}>
          {SPEEDS.map((s) => (
            <button key={s} type="button" aria-pressed={speed === s} onClick={() => onSpeed(s)}>
              {s}x
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label={t("top.mode")}>
          {(["normal", "advanced"] as const).map((m) => (
            <button key={m} type="button" aria-pressed={mode === m} onClick={() => onMode(m)}>
              {t(`top.mode.${m}`)}
            </button>
          ))}
        </div>
        {onHelp && <button type="button" className="ghost" onClick={onHelp}>{t("how.help")}</button>}
        {onTheme && (
          <button type="button" className="ghost" aria-pressed={!!dark} onClick={onTheme}>
            {dark ? t("theme.light") : t("theme.dark")}
          </button>
        )}
        {onDev && (
          <button type="button" className="ghost" aria-pressed={!!devOpen} onClick={onDev}>
            {t("top.dev")}
          </button>
        )}
      </div>
    </header>
  );
}
