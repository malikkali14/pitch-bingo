"""Normal-mode number ranges (spec 4.2): three ranges per count template and deadline, set from
generated matches so each range is about equally likely.

Run `python -m app.game.ranges` to rebuild ranges.json after a generator change.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.game.bank import FULL_S, TEMPLATES
from app.game.resolve import PREDICATES, YES_NO, Context, deadline_t

RANGES_PATH = Path(__file__).with_name("ranges.json")
SEEDS = 100
MINUTES = list(range(600, FULL_S + 1, 300))
COUNTED = [t.id for t in TEMPLATES.values()
           if t.normal == "number" and t.resolver in PREDICATES and t.resolver not in YES_NO]


def best_cuts(counts: list[int]) -> tuple[int, int]:
    """Cuts (a, b) for buckets 0..a-1, a..b-1 and b+, closest to a third each."""
    n = len(counts)
    top = max(max(counts), 1)
    share = [sum(1 for c in counts if c == k) / n for k in range(top + 2)]
    best: tuple[float, int, int] | None = None
    for a in range(1, top + 1):
        for b in range(a + 1, top + 2):
            parts = (sum(share[:a]), sum(share[a:b]), 1 - sum(share[:b]))
            err = sum((p - 1 / 3) ** 2 for p in parts)
            if best is None or err < best[0] - 1e-12:
                best = (err, a, b)
    assert best is not None
    return best[1], best[2]


def option_keys(cuts: tuple[int, int] | list[int]) -> list[str]:
    a, b = cuts
    low = "0" if a == 1 else f"0-{a - 1}"
    mid = str(a) if b == a + 1 else f"{a}-{b - 1}"
    return [low, mid, f"{b}+"]


def in_range(key: str, count: int) -> bool:
    if key.endswith("+"):
        return count >= int(key[:-1])
    lo, _, hi = key.partition("-")
    return int(lo) <= count <= int(hi or lo)


def range_of(keys: list[str], count: int) -> str:
    return next(k for k in keys if in_range(k, count))


def label(key: str) -> str:
    return key.replace("-", "–")


@lru_cache(maxsize=1)
def load() -> dict[str, dict[str, list[int]]]:
    data: dict[str, dict[str, list[int]]] = json.loads(RANGES_PATH.read_text())
    return data


def cuts_for(template_id: str, deadline_s: int) -> tuple[int, int]:
    table = load()[template_id]
    nearest = min(table, key=lambda m: abs(int(m) - deadline_s))
    a, b = table[nearest]
    return a, b


def compute(seeds: int = SEEDS) -> dict[str, Any]:
    from app.generator import generate

    samples: dict[str, dict[int, list[int]]] = {k: {m: [] for m in MINUTES} for k in COUNTED}
    for seed in range(1, seeds + 1):
        match = generate(seed, with_tracking=False)
        events = match["events"]
        home, away = match["match"]["home_team_id"], match["match"]["away_team_id"]
        half2 = next(e["t"] for e in events if e["type"] == "period_start" and e["period"] == 2)
        for template_id in COUNTED:
            test = PREDICATES[TEMPLATES[template_id].resolver]
            clubs = [home, away] if template_id == "club_fouls" else [None]
            for club in clubs:
                ctx = Context(home, away, club=club)
                for m in MINUTES:
                    until = deadline_t(m, half2)
                    assert until is not None
                    samples[template_id][m].append(
                        sum(1 for e in events if e["t"] <= until and test(e, ctx)))
    return {k: {str(m): list(best_cuts(v)) for m, v in per.items()} for k, per in samples.items()}


def main() -> None:
    table = compute()
    RANGES_PATH.write_text(json.dumps(table, indent=1) + "\n")
    print(f"wrote {RANGES_PATH}")
    for k, per in table.items():
        print(k, {m: option_keys(c) for m, c in per.items() if int(m) % 900 == 0})


if __name__ == "__main__":
    main()
