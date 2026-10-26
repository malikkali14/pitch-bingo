// Display clock (spec 3, top bar): mm:ss, with "45+2:10" style stoppage time.
// Frames carry only match seconds, so the clock is the last event's clock advanced by the
// match time since that event.

const HALF_S = 45 * 60;

/** Seconds into the current period, from a clock such as "23:15", "45+2:10" or "67:30". */
export function periodElapsed(clock: string, period: number): number {
  const [main, extra] = clock.split("+");
  const parts = (extra ?? main).split(":").map(Number);
  if (extra !== undefined) {
    return HALF_S + parts[0] * 60 + parts[1];
  }
  const total = parts[0] * 60 + parts[1];
  return period === 2 ? total - HALF_S : total;
}

export function formatClock(elapsed: number, period: number): string {
  const s = Math.max(0, Math.floor(elapsed));
  const base = period === 2 ? HALF_S : 0;
  if (s <= HALF_S) {
    const total = base + s;
    return `${pad(Math.floor(total / 60))}:${pad(total % 60)}`;
  }
  const over = s - HALF_S;
  return `${(base + HALF_S) / 60}+${Math.floor(over / 60)}:${pad(over % 60)}`;
}

export interface ClockAnchor {
  t: number;
  clock: string;
  period: number;
}

/** The clock at match time t, given the latest event seen. */
export function clockAt(anchor: ClockAnchor | null, t: number): string {
  if (!anchor) return formatClock(t, 1);
  return formatClock(periodElapsed(anchor.clock, anchor.period) + (t - anchor.t), anchor.period);
}

/** The minute shown in the feed: "23'", or "45+2'" in stoppage time. */
export function minuteLabel(clock: string): string {
  const [main, extra] = clock.split("+");
  if (extra !== undefined) return `${main}+${Number(extra.split(":")[0]) + 1}'`;
  return `${Number(main.split(":")[0]) + 1}'`;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}
