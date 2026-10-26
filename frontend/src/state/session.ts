// Starts a session (POST /api/sessions) and streams its WebSocket (spec 9.3, 9.4).

import { useCallback, useEffect, useReducer, useRef } from "react";
import type { ClientMessage, ServerMessage, Speed } from "../protocol";
import { FrameStore } from "./frames";
import { initialState, matchReducer, type MatchState } from "./match";

export interface MatchSession {
  state: MatchState;
  frames: FrameStore;
  setSpeed(speed: Speed): void;
  send(msg: ClientMessage): void;
}

export function socketUrl(sessionId: string, location: Location = window.location): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}/ws/sessions/${sessionId}`;
}

export function useMatchSession(seed?: number): MatchSession {
  const [state, dispatch] = useReducer(matchReducer, initialState);
  const frames = useRef(new FrameStore()).current;
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    (async () => {
      try {
        const response = await fetch("/api/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(seed === undefined ? {} : { seed }),
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
  }, [seed, frames]);

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

  return { state, frames, setSpeed, send };
}
