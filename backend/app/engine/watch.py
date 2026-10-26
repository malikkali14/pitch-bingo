"""Watch a running server's replay stream from the terminal.

python -m app.engine.watch [--url http://localhost:8000] [--seed 2610] [--seconds 5]
                           [--speeds 1 5 10]

Creates a session, opens its WebSocket, and for each speed prints how many frames, events
and stats arrived and how far match time moved.
"""

import argparse
import asyncio
import json
import time
from collections import Counter
from typing import Any

import httpx
import websockets


async def watch(url: str, seed: int, seconds: float, speeds: list[int]) -> None:
    async with httpx.AsyncClient(base_url=url) as client:
        response = await client.post("/api/sessions", json={"seed": seed})
        response.raise_for_status()
        session_id = response.json()["session_id"]
    ws_url = url.replace("http", "ws", 1) + f"/ws/sessions/{session_id}"
    async with websockets.connect(ws_url, max_size=None) as ws:
        ready = json.loads(await ws.recv())
        match = ready["match"]
        print(f"{ready['type']}: {match['match_id']} "
              f"{match['teams'][0]['name']} v {match['teams'][1]['name']}")
        for speed in speeds:
            await ws.send(json.dumps({"type": "replay.speed", "speed": speed}))
            counts: Counter[str] = Counter()
            last: dict[str, Any] = {}
            first_t = None
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                msg = json.loads(await ws.recv())
                counts[msg["type"]] += 1
                last[msg["type"]] = msg
                if msg["type"] == "frame" and first_t is None:
                    first_t = msg["t"]
            frame_t = last.get("frame", {}).get("t", 0.0)
            moved = frame_t - (first_t or 0.0)
            print(f"{speed:>2}x  {dict(counts)}  match time {moved:.1f} s in {seconds:.0f} s "
                  f"(x{moved / seconds:.1f})")
            if "event" in last:
                event = last["event"]["event"]
                print(f"     last event {event['clock']} {event['type']} "
                      f"(significance {last['event']['significance']})")
            if "stats" in last:
                stats = last["stats"]
                print(f"     score {stats['score']}  possession "
                      f"{ {k: v['possession'] for k, v in stats['clubs'].items()} }  "
                      f"chaos {stats['patterns']['chaos']['value']}  "
                      f"momentum {stats['patterns']['momentum']['value']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--seed", type=int, default=2610)
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--speeds", type=int, nargs="+", default=[1, 5, 10])
    args = parser.parse_args()
    asyncio.run(watch(args.url, args.seed, args.seconds, args.speeds))


if __name__ == "__main__":
    main()
