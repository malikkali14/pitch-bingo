"""Percentiles from the validation matches for chaos (spec 7.4) and the tempo label (7.6).

python -m app.stats.calibrate [--seeds 50]

Runs the stats engine over the events of seeds 1..N (the same seeds validate.py uses), samples
the raw chaos inputs and events per in-play minute once a match minute after their windows are
full, and writes the 10th/90th percentiles and the terciles to calibration.json.
"""

import argparse
import json
from typing import Any

import numpy as np

from app.generator import generate
from app.stats.engine import CALIBRATION_PATH, StatsEngine
from app.stats.patterns import Chaos, Rhythm

# Raw inputs don't depend on the calibration, so any placeholder works while sampling.
PLACEHOLDER = {"chaos": {k: [0.0, 1.0] for k in "TDCS"}, "tempo_terciles": [0.0, 1.0]}
SAMPLE_EVERY_S = 60.0


def samples(meta: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, list[float]]:
    engine = StatsEngine(meta, calibration=PLACEHOLDER)
    out: dict[str, list[float]] = {k: [] for k in [*"TDCS", "tempo"]}
    next_sample = Chaos.SPAN
    for event in events:
        engine.on_event(event)
        if event["t"] < next_sample:
            continue
        next_sample += SAMPLE_EVERY_S
        for key, value in engine.chaos.inputs.items():
            if value is not None:
                out[key].append(value)
        epm = engine.rhythm.values["events_per_min"]
        if event["t"] >= Rhythm.SPAN and epm is not None:
            out["tempo"].append(epm)
    return out


def calibrate(seeds: int) -> dict[str, Any]:
    pooled: dict[str, list[float]] = {k: [] for k in [*"TDCS", "tempo"]}
    for seed in range(1, seeds + 1):
        match = generate(seed, with_tracking=False)
        for key, values in samples(match["match"], match["events"]).items():
            pooled[key] += values
    return {
        "source": f"stats engine over the events of seeds 1-{seeds}, sampled every minute",
        "chaos": {k: [round(float(np.percentile(pooled[k], q)), 4) for q in (10, 90)]
                  for k in "TDCS"},
        "tempo_terciles": [round(float(np.percentile(pooled["tempo"], q)), 3)
                           for q in (100 / 3, 200 / 3)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=50)
    args = parser.parse_args()
    result = calibrate(args.seeds)
    CALIBRATION_PATH.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
