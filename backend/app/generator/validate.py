"""Check the generator against the calibration targets in spec 6.8.

python -m app.generator.validate --seeds 50 [--chart ../docs/validation.png]
"""

import argparse
import statistics
from pathlib import Path
from typing import Any

from app.generator import generate

# measure -> (low, high) for the mean over all seeds. Possession is checked per club.
RANGES: dict[str, tuple[float, float]] = {
    "passes": (850, 1050),
    "pass_completion": (0.78, 0.86),
    "shots": (20, 30),
    "shots_on_target_pct": (0.30, 0.40),
    "goals": (2.2, 3.4),
    "xg_total": (2.0, 3.6),
    "fouls": (18, 26),
    "yellow_cards": (2, 6),
    "red_cards": (0.02, 0.25),
    "corners": (8, 12),
    "offsides": (2, 6),
    "throw_ins": (35, 50),
    "substitutions": (6, 10),
    "tackles": (25, 40),
    "interceptions": (15, 30),
    "possession_min": (0.35, 0.65),
    "possession_max": (0.35, 0.65),
    "ball_in_play_min": (52, 60),
    "distance_per_outfield_km": (9, 12),
    "top_speed_kmh": (30, 36),
}

# Measured from tracking; skipped while the simple movement model is in place.
TRACKING_MEASURES = {"distance_per_outfield_km", "top_speed_kmh"}


def measures(summary: dict[str, Any]) -> dict[str, float]:
    values = {k: float(summary[k]) for k in RANGES if k in summary}
    poss = list(summary["possession"].values())
    values["possession_min"], values["possession_max"] = min(poss), max(poss)
    return values


def run(seeds: int, with_tracking: bool = False) -> tuple[dict[str, list[float]], list[str]]:
    samples: dict[str, list[float]] = {k: [] for k in RANGES}
    model = "fallback"
    for seed in range(1, seeds + 1):
        summary = generate(seed, with_tracking=with_tracking)["summary"]
        model = summary["tracking_model"]
        for k, v in measures(summary).items():
            samples[k].append(v)
    failures = []
    for k, (lo, hi) in RANGES.items():
        if not samples[k] or (k in TRACKING_MEASURES and model == "fallback"):
            continue
        mean = statistics.fmean(samples[k])
        if not lo <= mean <= hi:
            failures.append(f"{k}: mean {mean:.3f} outside {lo}-{hi}")
    return samples, failures


def chart(samples: dict[str, list[float]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    keys = [k for k in RANGES if samples[k]]
    cols = 4
    rows = -(-len(keys) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(14, 2.6 * rows))
    for ax, key in zip(axes.flat, keys, strict=False):
        lo, hi = RANGES[key]
        ax.hist(samples[key], bins=12, color="#1F4E9C")
        ax.axvspan(lo, hi, color="#F2C230", alpha=0.25)
        ax.axvline(statistics.fmean(samples[key]), color="#B3262E")
        ax.set_title(key, fontsize=9)
    for ax in list(axes.flat)[len(keys):]:
        ax.axis("off")
    fig.suptitle("Generator calibration: distributions (bars), target range (band), mean (line)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=50)
    parser.add_argument("--tracking", action="store_true", help="also check tracking measures")
    parser.add_argument("--chart", type=Path, default=None)
    args = parser.parse_args()
    samples, failures = run(args.seeds, args.tracking)
    for k, (lo, hi) in RANGES.items():
        if samples[k]:
            mean = statistics.fmean(samples[k])
            flag = "ok " if lo <= mean <= hi else "OUT"
            print(f"{flag} {k:26s} mean {mean:9.3f}   target {lo}-{hi}")
    if args.chart:
        chart(samples, args.chart)
        print(f"chart saved to {args.chart}")
    if failures:
        raise SystemExit("validation failed:\n  " + "\n  ".join(failures))
    print("validation passed")


if __name__ == "__main__":
    main()
