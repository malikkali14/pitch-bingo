"""Seeded synthetic match generator (spec 6). The same seed always gives the same files."""

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.generator import movement
from app.generator.metadata import build_metadata
from app.generator.sim import Sim
from app.generator.summary import summarize


def generate(seed: int, plants: dict[int, str] | None = None,
             with_tracking: bool = True) -> dict[str, Any]:
    """Build one match. `plants` maps a segment (0-4) to a scenario in planted.SCENARIOS."""
    meta = build_metadata(seed)
    sim = Sim(meta, seed)
    for segment, scenario in (plants or {}).items():
        sim.plant(segment, scenario)
    events = sim.run()
    tracking = movement.simulate_tracking(meta, events) if with_tracking else None
    summary = summarize(meta, events, sim.in_play_s, sim.on_ball_s, tracking)
    summary["planted"] = [sim.planted[k] for k in sorted(sim.planted)]
    return {"match": meta, "events": events, "tracking": tracking, "summary": summary}


def write_match(result: dict[str, Any], out: Path) -> Path:
    folder = out / str(result["match"]["seed"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "match.json").write_text(json.dumps(result["match"], indent=2) + "\n")
    with (folder / "events.jsonl").open("w") as f:
        for event in result["events"]:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
    (folder / "summary.json").write_text(json.dumps(result["summary"], indent=2) + "\n")
    if result["tracking"] is not None:
        # Plain np.savez keeps the zip timestamps fixed, so files are byte-identical per seed.
        with (folder / "tracking.npz").open("wb") as f:
            np.savez_compressed(f, **result["tracking"])
    return folder
