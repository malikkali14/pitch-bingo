// The pitch (spec 3): SVG in metres, 105 x 68, animated with requestAnimationFrame.

import { useEffect, useState } from "react";
import { t } from "../i18n";
import type { MatchEvent } from "../protocol";
import { attacksRight, type Roster } from "../roster";
import type { Positions, FrameStore } from "../state/frames";
import { carrierAt, type BallState } from "../state/ball";
import type { Cue } from "../state/match";

const LENGTH = 105;
const WIDTH = 68;
const ARROW_MS = 2000;
const CUE_MS = 2500;
const FLASH_MS = 900;
const LABEL_RADIUS_M = 15;
const CARRIER_RADIUS_M = 3; // ring the carrier only once they are actually on the ball

interface Props {
  roster: Roster;
  frames: FrameStore;
  cues: Cue[];
  cards: Record<string, "yellow" | "red">;
  ball: BallState;
  reducedMotion: boolean;
  /** The fan's focus player: ringed and always named. */
  focusId?: string | null;
  /** Set while a "who" square is open: tapping a dot answers it (spec 3). */
  onPick?: (playerId: string) => void;
}

export function Pitch({ roster, frames, cues, cards, ball, reducedMotion, focusId, onPick }: Props) {
  const [view, setView] = useState<{ pos: Positions | null; now: number }>({ pos: null, now: 0 });

  useEffect(() => {
    let id = 0;
    const draw = () => {
      const now = performance.now();
      setView({ pos: frames.at(now, !reducedMotion), now });
      id = requestAnimationFrame(draw);
    };
    id = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(id);
  }, [frames, reducedMotion]);

  const { pos, now } = view;
  const recent = cues.filter((c) => now - c.at < CUE_MS);
  const named = new Set<string>();
  for (const { event } of recent.slice(-3)) {
    if (event.player_id) named.add(event.player_id);
    if (typeof event.receiver_id === "string") named.add(event.receiver_id);
  }
  const goal = recent.find((c) => c.event.type === "goal" && now - c.at < FLASH_MS);
  const carrierId = pos ? carrierAt(ball, pos.t) : null;
  const carrierXY = carrierId ? pos?.players.get(carrierId) : undefined;
  const carrier = carrierXY && pos &&
    Math.hypot(carrierXY[0] - pos.ball[0], carrierXY[1] - pos.ball[1]) <= CARRIER_RADIUS_M
    ? carrierId : null;
  if (carrier) named.add(carrier);
  if (focusId) named.add(focusId);

  return (
    <div className="pitch-wrap keep-light">
    {ball.stoppage && <p className="stoppage" role="status">{ball.stoppage}</p>}
    <svg
      className="pitch"
      viewBox={`-3 -3 ${LENGTH + 6} ${WIDTH + 6}`}
      role="img"
      aria-label={t("pitch.label", { home: roster.home.name, away: roster.away.name })}
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4"
          orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="arrowhead" />
        </marker>
      </defs>
      <Markings />
      {goal && !reducedMotion && <rect className="goal-flash" x={0} y={0} width={LENGTH} height={WIDTH} />}
      {recent.map((c) => (
        <CueMark key={c.event.event_id} cue={c} now={now} homeId={roster.home.id}
          reducedMotion={reducedMotion} />
      ))}
      {pos &&
        [...pos.players].map(([id, [x, y]]) => {
          const player = roster.players.get(id);
          return (
            <PlayerDot key={id} x={x} y={y} home={player?.home ?? true}
              keeper={player?.position === "GK"} number={player?.shirt_number} card={cards[id]}
              carrier={id === carrier} focus={id === focusId} name={player?.full_name}
              onPick={onPick ? () => onPick(id) : undefined} />
          );
        })}
      {pos && <circle className="ball" cx={pos.ball[0]} cy={pos.ball[1]} r={0.75} />}
      {/* Names sit above every dot; the carrier's goes last so it is never covered. */}
      {pos &&
        [...pos.players]
          .filter(([id, [x, y]]) =>
            named.has(id) || Math.hypot(x - pos.ball[0], y - pos.ball[1]) <= LABEL_RADIUS_M)
          .sort(([a], [b]) => Number(a === carrier) - Number(b === carrier))
          .map(([id, [x, y]]) => (
            <text key={id} className={`name${id === carrier ? " carrier" : ""}`} x={x} y={y - 2.1}
              textAnchor="middle">
              {roster.players.get(id)?.surname}
            </text>
          ))}
    </svg>
    </div>
  );
}

function Markings() {
  return (
    <g className="markings">
      <rect className="grass" x={-3} y={-3} width={LENGTH + 6} height={WIDTH + 6} />
      <rect x={0} y={0} width={LENGTH} height={WIDTH} />
      <line x1={LENGTH / 2} y1={0} x2={LENGTH / 2} y2={WIDTH} />
      <circle cx={LENGTH / 2} cy={WIDTH / 2} r={9.15} />
      <circle className="spot" cx={LENGTH / 2} cy={WIDTH / 2} r={0.3} />
      {[0, LENGTH].map((gx) => {
        const dir = gx === 0 ? 1 : -1;
        const box = (depth: number, half: number) => (
          <rect x={Math.min(gx, gx + dir * depth)} y={WIDTH / 2 - half} width={depth} height={half * 2} />
        );
        return (
          <g key={gx}>
            {box(16.5, 20.16)}
            {box(5.5, 9.16)}
            <circle className="spot" cx={gx + dir * 11} cy={WIDTH / 2} r={0.3} />
            <rect className="goal" x={gx === 0 ? -2 : LENGTH} y={WIDTH / 2 - 3.66} width={2} height={7.32} />
          </g>
        );
      })}
    </g>
  );
}

interface DotProps {
  x: number;
  y: number;
  home: boolean;
  keeper: boolean;
  number?: number;
  card?: "yellow" | "red";
  carrier?: boolean;
  focus?: boolean;
  name?: string;
  onPick?: () => void;
}

function PlayerDot({ x, y, home, keeper, number, card, carrier, focus, name, onPick }: DotProps) {
  const r = 1.4;
  const cls = `dot ${home ? "home" : "away"}${keeper ? " keeper" : ""}${carrier ? " carrier" : ""}` +
    (onPick ? " pickable" : "");
  const pick = onPick
    ? { role: "button", tabIndex: 0, "aria-label": name, onClick: onPick,
        onKeyDown: (e: { key: string }) => (e.key === "Enter" || e.key === " ") && onPick() }
    : {};
  return (
    <g className={cls} transform={`translate(${x} ${y})`} {...pick}>
      {focus && <circle className="focus-ring" r={r + 1.5} />}
      {carrier && <circle className="carrier-ring" r={r + 0.9} />}
      {home ? (
        <circle className="body" r={r} />
      ) : (
        <rect className="body" x={-r} y={-r} width={r * 2} height={r * 2} rx={0.5} />
      )}
      {number !== undefined && (
        <text className="number" textAnchor="middle" dominantBaseline="central">
          {number}
        </text>
      )}
      {card && <rect className={`card-badge ${card}`} x={0.8} y={-2.3} width={0.9} height={1.2} rx={0.15} />}
    </g>
  );
}

const CUE_TYPES = ["foul", "advantage", "offside", "corner", "substitution", "goal"];

function CueMark({ cue, now, homeId, reducedMotion }: { cue: Cue; now: number; homeId: string; reducedMotion: boolean }) {
  const e: MatchEvent = cue.event;
  const age = now - cue.at;
  if (e.type === "pass") {
    if (age > ARROW_MS) return null;
    const ok = e.outcome === "complete";
    return (
      <line className={`pass${ok ? "" : " failed"}`} x1={e.x} y1={e.y} x2={Number(e.end_x)} y2={Number(e.end_y)}
        opacity={reducedMotion ? 1 : 1 - age / ARROW_MS} markerEnd="url(#arrow)" />
    );
  }
  if (e.type === "shot") {
    const goalX = attacksRight(e.team_id, e.period, homeId) ? LENGTH : 0;
    const goalY = typeof e.goal_y === "number" ? e.goal_y : WIDTH / 2;
    return (
      <g className="shot">
        <line x1={e.x} y1={e.y} x2={goalX} y2={goalY} markerEnd="url(#arrow)" />
        <Badge x={(e.x + goalX) / 2} y={(e.y + goalY) / 2 - 2} text={t("pitch.kmh", { speed: Number(e.ball_speed_kmh).toFixed(0) })} />
      </g>
    );
  }
  const text = CUE_TYPES.includes(e.type) ? t(`pitch.cue.${e.type}`) : null;
  return text ? <Badge x={e.x} y={e.y - 3} text={text} /> : null;
}

function Badge({ x, y, text }: { x: number; y: number; text: string }) {
  const width = text.length * 0.95 + 1.6;
  const cx = Math.min(LENGTH - width / 2, Math.max(width / 2, x));
  const cy = Math.min(WIDTH, Math.max(1.5, y));
  return (
    <g className="cue" transform={`translate(${cx} ${cy})`}>
      <rect x={-width / 2} y={-1.4} width={width} height={2.8} rx={1.4} />
      <text textAnchor="middle" dominantBaseline="central">
        {text}
      </text>
    </g>
  );
}
