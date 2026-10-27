import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { FrameStore } from "./state/frames";

const REDUCED = "(prefers-reduced-motion: reduce)";

/** Follows the system reduced-motion setting (spec 3, accessibility). */
export function usePrefersReducedMotion(): boolean {
  const query = () => typeof window !== "undefined" && !!window.matchMedia?.(REDUCED).matches;
  const [reduced, setReduced] = useState(query);
  useEffect(() => {
    const list = window.matchMedia?.(REDUCED);
    if (!list) return;
    const onChange = () => setReduced(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

/** Match time of the latest frame; re-renders only the component that asks. */
export function useFrameTime(frames: FrameStore): number {
  return useSyncExternalStore(
    (fn) => frames.subscribe(fn),
    () => frames.latest()?.t ?? 0,
  );
}

/** Wall clock in ms, ticking every `ms`. */
export function useNow(ms = 250): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

/** A short chime when an announced window opens (spec 3). Silent where audio isn't allowed. */
export function useChime(trigger: string): void {
  const context = useRef<AudioContext | null>(null);
  useEffect(() => {
    if (!trigger || typeof window === "undefined" || !("AudioContext" in window)) return;
    try {
      context.current ??= new AudioContext();
      const ctx = context.current;
      const tone = ctx.createOscillator();
      const gain = ctx.createGain();
      tone.frequency.value = 880;
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.25);
      tone.connect(gain).connect(ctx.destination);
      tone.start();
      tone.stop(ctx.currentTime + 0.25);
    } catch {
      // No audio: the pulse and the screen-reader announcement still mark the window.
    }
  }, [trigger]);
}
