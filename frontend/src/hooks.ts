import { useEffect, useState, useSyncExternalStore } from "react";
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
