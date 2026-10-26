// Position frames arrive ten times a second. The pitch interpolates between the last two
// (spec 3: "the client interpolates between position frames"), drawing one frame behind.

import type { FrameMessage } from "../protocol";

export interface Positions {
  t: number;
  ball: [number, number, number];
  players: Map<string, [number, number]>;
}

/** A jump of more than this many match seconds snaps instead of gliding (dev jumps). */
const SNAP_S = 3;

export class FrameStore {
  private prev: { frame: FrameMessage; at: number } | null = null;
  private curr: { frame: FrameMessage; at: number } | null = null;
  private listeners = new Set<() => void>();

  push(frame: FrameMessage, at: number): void {
    this.prev = this.curr;
    this.curr = { frame, at };
    this.listeners.forEach((fn) => fn());
  }

  latest(): FrameMessage | null {
    return this.curr?.frame ?? null;
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** Positions at wall time `now` (ms). With `smooth` off, the latest frame as it is. */
  at(now: number, smooth = true): Positions | null {
    const curr = this.curr;
    if (!curr) return null;
    const prev = this.prev;
    if (!smooth || !prev || Math.abs(curr.frame.t - prev.frame.t) > SNAP_S) {
      return toPositions(curr.frame);
    }
    const span = Math.max(1, curr.at - prev.at);
    const a = Math.min(1, Math.max(0, (now - curr.at) / span));
    return lerpFrames(prev.frame, curr.frame, a);
  }
}

export function toPositions(frame: FrameMessage): Positions {
  return {
    t: frame.t,
    ball: frame.ball,
    players: new Map(frame.players.map(([id, x, y]) => [id, [x, y]])),
  };
}

export function lerpFrames(a: FrameMessage, b: FrameMessage, alpha: number): Positions {
  const from = new Map(a.players.map(([id, x, y]) => [id, [x, y] as const]));
  const lerp = (p: number, q: number) => p + (q - p) * alpha;
  const players = new Map<string, [number, number]>();
  for (const [id, x, y] of b.players) {
    const start = from.get(id);
    players.set(id, start ? [lerp(start[0], x), lerp(start[1], y)] : [x, y]);
  }
  return {
    t: lerp(a.t, b.t),
    ball: [lerp(a.ball[0], b.ball[0]), lerp(a.ball[1], b.ball[1]), lerp(a.ball[2], b.ball[2])],
    players,
  };
}
