"""python -m app.generator --seed 2610 --out data/matches"""

import argparse
from pathlib import Path

from app.generator import generate, write_match


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic matches.")
    parser.add_argument("--seed", type=int, nargs="+", default=[2610])
    parser.add_argument("--out", type=Path, default=Path("data/matches"))
    parser.add_argument("--no-tracking", action="store_true", help="skip tracking.npz")
    args = parser.parse_args()
    for seed in args.seed:
        result = generate(seed, with_tracking=not args.no_tracking)
        folder = write_match(result, args.out)
        s = result["summary"]
        score = " - ".join(str(v) for v in s["score"].values())
        print(f"seed {seed}: {score}, {s['passes']} passes, {s['shots']} shots -> {folder}")


if __name__ == "__main__":
    main()
