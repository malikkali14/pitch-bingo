"""Play a whole match through the API, with no browser and no LLM.

    python -m app.game.play --url http://localhost:8000 --mode normal --speed 10

A bot viewer: it answers a first-to-happen square as soon as it sees the event, guesses on
deadline and live windows a second or two after they open, applies the strategist's advice,
and prints the card and leaderboard at full time. At 10x a match takes about ten minutes.
"""

import argparse
import asyncio
import json
import random
import time
import urllib.request
from typing import Any

import websockets

from app.game.resolve import matches

FULL_TIME_GRACE_S = 22.0     # windows open at full time still run their 20 seconds


def create_session(url: str, seed: int, profile: dict[str, Any]) -> str:
    request = urllib.request.Request(
        f"{url}/api/sessions", data=json.dumps({"seed": seed, "profile": profile}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request) as response:
        return str(json.load(response)["session_id"])


def first_answer(square: dict[str, Any], event: dict[str, Any]) -> str:
    if square["answer_type"] == "team":
        return str(event["team_id"])
    field = {"first_sub_off": "player_off_id", "first_scorer": "scorer_id"}.get(
        square["resolver"], "player_id")
    return str(event[field])


def guess(square: dict[str, Any], rng: random.Random) -> str:
    if square["options"]:
        return rng.choice(square["options"])
    return str(rng.randint(0, 3))


class Bot:
    def __init__(self, ws: Any, rng: random.Random, verbose: bool) -> None:
        self.ws = ws
        self.rng = rng
        self.verbose = verbose
        self.squares: dict[str, dict[str, Any]] = {}
        self.answered: set[str] = set()
        self.board: dict[str, Any] = {}
        self.leaderboard: list[dict[str, Any]] = []
        self.clock = "00:00"
        self.tasks: set[asyncio.Task[None]] = set()

    def later(self, square_id: str, value: str, delay: float) -> None:
        task = asyncio.create_task(self.answer(square_id, value, delay))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def log(self, text: str) -> None:
        if self.verbose:
            print(f"{self.clock:>8}  {text}")

    async def answer(self, square_id: str, value: str, delay: float = 0.0) -> None:
        if square_id in self.answered:
            return
        self.answered.add(square_id)
        await asyncio.sleep(delay)
        await self.ws.send(json.dumps({"type": "answer.submit", "square_id": square_id,
                                       "value": value}))

    async def handle(self, msg: dict[str, Any]) -> bool:
        """Returns True at full time."""
        kind = msg["type"]
        if kind == "session.ready":
            self.board = msg["card"]
            self.squares = {s["id"]: s for s in msg["card"]["squares"]}
        elif kind == "event":
            event = msg["event"]
            self.clock = event["clock"]
            for sq in self.squares.values():
                if sq["kind"] == "first" and sq["state"] == "waiting" and sq["trigger"] and \
                        matches(sq["trigger"], event) and sq["id"] not in self.answered:
                    self.later(sq["id"], first_answer(sq, event), 1.0)
            if event["type"] == "period_end" and event["period"] == 2:
                return True
        elif kind == "square.added":
            sq = msg["square"]
            self.squares[sq["id"]] = sq
            self.log(f"live square: {sq['text']['en']} {sq['options']}")
        elif kind == "square.window_open":
            sq = self.squares[msg["square_id"]]
            delay = self.rng.uniform(1.0, 6.0)
            self.later(sq["id"], guess(sq, self.rng), delay)
        elif kind == "square.result":
            sq = self.squares.get(msg["square_id"], {})
            self.log(f"{msg['status']:>9} {msg['points']:>4} pts  {sq.get('text', {}).get('en')}"
                     f"  (answer: {msg['correct_answer']})")
        elif kind == "board.update":
            self.board = msg
            self.squares = {s["id"]: s for s in msg["squares"]}
        elif kind == "board.line":
            self.log(f"LINE {msg['line']} +{msg['points']}"
                     + (" (Blank slate)" if msg["blank_slate"] else ""))
        elif kind == "strategy.advice":
            self.log(f"strategist: {msg['reason']} "
                     f"({msg['before']:.0%} -> {msg['after']:.0%})"
                     + (" [applied]" if msg["applied"] else ""))
            if not msg["applied"]:
                await self.ws.send(json.dumps({"type": "strategy.apply",
                                               "advice_id": msg["advice_id"]}))
        elif kind == "leaderboard":
            self.leaderboard = msg["rows"]
        elif kind == "error":
            self.log(f"error from {msg['request']}: {msg['reason']}")
        return False

    def summary(self) -> str:
        squares = self.board.get("squares", [])
        counts: dict[str, int] = {}
        for sq in squares:
            counts[sq["state"]] = counts.get(sq["state"], 0) + 1
        lines = [f"points {self.board.get('points')}, correct {self.board.get('correct')}, "
                 f"lines {self.board.get('scored_lines')}",
                 "states: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())),
                 "leaderboard:"]
        for row in self.leaderboard:
            mark = "  <- you" if row["you"] else ""
            lines.append(f"  {row['rank']:>2}. {row['handle']:<18} {row['points']:>6}{mark}")
        return "\n".join(lines)


async def play(args: argparse.Namespace) -> None:
    profile = {"mode": args.mode, "strategist": args.strategist, "handle": "Bot"}
    session_id = create_session(args.url, args.seed, profile)
    ws_url = args.url.replace("http", "ws", 1) + f"/ws/sessions/{session_id}"
    print(f"session {session_id}, seed {args.seed}, {args.mode} mode, {args.speed}x")
    started = time.monotonic()
    async with websockets.connect(ws_url, max_size=None) as ws:
        bot = Bot(ws, random.Random(args.seed), not args.quiet)
        await ws.send(json.dumps({"type": "replay.speed", "speed": args.speed}))
        full_time = False
        async for raw in ws:
            if await bot.handle(json.loads(raw)):
                full_time = True
                break
        if full_time:
            end = time.monotonic() + FULL_TIME_GRACE_S
            while time.monotonic() < end:
                try:
                    raw = await asyncio.wait_for(ws.recv(), end - time.monotonic())
                except TimeoutError:
                    break
                await bot.handle(json.loads(raw))
    print(f"\nfull time after {time.monotonic() - started:.0f} s\n{bot.summary()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play a match through the API.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--seed", type=int, default=2610)
    parser.add_argument("--mode", choices=["normal", "advanced"], default="normal")
    parser.add_argument("--strategist", choices=["auto", "suggest", "manual"], default="suggest")
    parser.add_argument("--speed", type=int, choices=[1, 5, 10], default=10)
    parser.add_argument("--quiet", action="store_true", help="only print the summary")
    asyncio.run(play(parser.parse_args()))


if __name__ == "__main__":
    main()
