// Starts a session (POST /api/sessions) and streams its WebSocket (spec 9.3, 9.4).

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import type { Cell } from "../card/types";
import type { ClientMessage, Profile, ServerMessage, Speed } from "../protocol";
import { FrameStore } from "./frames";
import { initialState, matchReducer, type MatchState } from "./match";

/** What the setup screen chooses (spec 5.7); the server fills in the rest. */
export type ProfileChoice = Partial<Pick<Profile, "mode" | "club" | "focus_player_id" | "handle">>;

export interface Kickoff {
  seed?: number;
  profile: ProfileChoice;
}

export interface MatchSession {
  state: MatchState;
  frames: FrameStore;
  setSpeed(speed: Speed): void;
  send(msg: ClientMessage): void;
  answer(squareId: string, value: string): void;
  move(from: Cell, to: Cell): void;
  applyAdvice(adviceId: string): void;
  catchUp(): void;
  define(term: string | null): void;
  dev: {
    pause(on: boolean): void;
    jump(minute: number): void;
    narratorDown(on: boolean): void;
  };
}

export function socketUrl(sessionId: string, location: Location = window.location): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/ws/sessions/${sessionId}`;
}

/** Nothing happens until `kickoff` is set, so the setup screen can come first. */
export function useMatchSession(kickoff: Kickoff | null): MatchSession {
  const [state, dispatch] = useReducer(matchReducer, initialState);
  const frames = useRef(new FrameStore()).current;
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!kickoff) return;
    let closed = false;
    (async () => {
      try {
        const response = await fetch("/api/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(kickoff),
        });
        if (!response.ok) throw new Error(`POST /api/sessions: ${response.status}`);
        const { session_id } = (await response.json()) as { session_id: string };
        if (closed) return;
        const ws = new WebSocket(socketUrl(session_id));
        socket.current = ws;
        ws.onmessage = (e) => {
          const msg = JSON.parse(String(e.data)) as ServerMessage;
          if (msg.type === "frame") frames.push(msg, performance.now());
          else dispatch({ kind: "message", msg, now: performance.now() });
        };
        ws.onerror = () => dispatch({ kind: "status", status: "error" });
        ws.onclose = () => {
          if (!closed) dispatch({ kind: "status", status: "error" });
        };
      } catch {
        if (!closed) dispatch({ kind: "status", status: "error" });
      }
    })();
    return () => {
      closed = true;
      socket.current?.close();
      socket.current = null;
    };
  }, [kickoff, frames]);

  const send = useCallback((msg: ClientMessage) => {
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify(msg));
  }, []);

  const setSpeed = useCallback(
    (speed: Speed) => {
      send({ type: "replay.speed", speed });
      dispatch({ kind: "speed", speed });
    },
    [send],
  );

  const answer = useCallback(
    (squareId: string, value: string) => {
      send({ type: "answer.submit", square_id: squareId, value });
      dispatch({ kind: "answer", squareId, value });
    },
    [send],
  );

  const move = useCallback(
    (from: Cell, to: Cell) => {
      send({ type: "board.move", from_cell: from, to_cell: to });
      dispatch({ kind: "moved" });
    },
    [send],
  );

  const applyAdvice = useCallback(
    (adviceId: string) => {
      send({ type: "strategy.apply", advice_id: adviceId });
      dispatch({ kind: "moved" });
    },
    [send],
  );

  const dev = useMemo(() => ({
    pause: (on: boolean) => {
      send({ type: "dev.pause", on });
      dispatch({ kind: "dev", paused: on });
    },
    jump: (minute: number) => send({ type: "dev.jump", minute }),
    narratorDown: (on: boolean) => {
      send({ type: "dev.narrator_down", on });
      dispatch({ kind: "dev", narratorDown: on });
    },
  }), [send]);

  const catchUp = useCallback(() => send({ type: "recap.request", kind: "catch_up" }), [send]);
  const define = useCallback((term: string | null) => {
    dispatch({ kind: "define", term });
    if (term !== null) send({ type: "definition.request", term });
  }, [send]);

  return { state, frames, setSpeed, send, answer, move, applyAdvice, catchUp, define, dev };
}
