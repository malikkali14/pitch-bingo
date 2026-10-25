"""Match metadata: clubs, players, lineups, referee, venue and weather (spec 6.2)."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from app.generator.names import COACHES, FIRST_NAMES, REFEREE_NAMES, SURNAMES, VENUES, WEATHER

# Formation spots in each club's attacking frame: u runs 0 (own goal) to 105, v 0 to 68.
FORMATIONS: dict[str, list[tuple[str, float, float]]] = {
    "4-3-3": [
        ("GK", 5, 34), ("RB", 28, 8), ("CB", 22, 25), ("CB", 22, 43), ("LB", 28, 60),
        ("DM", 40, 34), ("CM", 52, 20), ("CM", 52, 48),
        ("RW", 75, 10), ("ST", 82, 34), ("LW", 75, 58),
    ],
    "4-2-3-1": [
        ("GK", 5, 34), ("RB", 28, 8), ("CB", 22, 25), ("CB", 22, 43), ("LB", 28, 60),
        ("DM", 42, 24), ("DM", 42, 44),
        ("RW", 68, 10), ("AM", 66, 34), ("LW", 68, 58), ("ST", 82, 34),
    ],
}

BENCH_POSITIONS = ["GK", "CB", "RB", "CM", "DM", "AM", "LW", "RW", "ST"]

CLUBS = [
    {
        "id": "NBA",
        "name": "Northbridge Athletic",
        "short_name": "Northbridge",
        "primary_color": "#1F4E9C",
        "secondary_color": "#F2C230",
        "formation": "4-3-3",
    },
    {
        "id": "KVL",
        "name": "Kestrel Vale",
        "short_name": "Kestrel",
        "primary_color": "#B3262E",
        "secondary_color": "#FFFFFF",
        "formation": "4-2-3-1",
    },
]


def _attributes(rng: random.Random, position: str) -> dict[str, int]:
    def roll(mean: float) -> int:
        return max(35, min(95, round(rng.gauss(mean, 7))))

    attacker = position in {"ST", "LW", "RW", "AM"}
    defender = position in {"CB", "RB", "LB", "DM", "GK"}
    return {
        "pace": roll(78 if position in {"LW", "RW", "RB", "LB", "ST"} else 68),
        "passing": roll(76 if position in {"CM", "DM", "AM"} else 66),
        "shooting": roll(78 if attacker else 52),
        "defending": roll(76 if defender else 48),
        "discipline": roll(70),
    }


def _player(
    rng: random.Random, club_id: str, index: int, position: str, used: set[str], shirt: int
) -> dict[str, Any]:
    while True:
        first, surname = rng.choice(FIRST_NAMES), rng.choice(SURNAMES)
        if surname not in used:
            used.add(surname)
            break
    attrs = _attributes(rng, position)
    starter_apps = rng.randint(4, 12)
    goal_rate = {"ST": 0.45, "LW": 0.3, "RW": 0.3, "AM": 0.25, "CM": 0.1}.get(position, 0.03)
    return {
        "id": f"{club_id}-{index:02d}",
        "full_name": f"{first} {surname}",
        "surname": surname,
        "shirt_number": shirt,
        "position": position,
        "preferred_foot": "left" if rng.random() < 0.25 else "right",
        "age": rng.randint(18, 34),
        "attributes": attrs,
        "top_speed_kmh": round(28 + 7 * (attrs["pace"] - 35) / 60, 1),
        "season": {
            "appearances": starter_apps,
            "goals": sum(rng.random() < goal_rate for _ in range(starter_apps)),
            "assists": sum(rng.random() < goal_rate * 0.6 for _ in range(starter_apps)),
            "yellow_cards": sum(rng.random() < 0.12 for _ in range(starter_apps)),
        },
    }


def _club(rng: random.Random, base: dict[str, Any], used: set[str]) -> dict[str, Any]:
    spots = FORMATIONS[base["formation"]]
    shirts = rng.sample(range(2, 40), 19)
    players = [
        _player(rng, base["id"], i + 1, pos, used, 1 if pos == "GK" else shirts.pop())
        for i, (pos, _, _) in enumerate(spots)
    ]
    players += [
        _player(rng, base["id"], 12 + i, pos, used, shirts.pop())
        for i, pos in enumerate(BENCH_POSITIONS)
    ]
    style = {k: round(rng.uniform(0.3, 0.8), 2) for k in
             ("possession", "pressing", "tempo", "directness")}
    return {
        **base,
        "coach": rng.choice(COACHES),
        "style": style,
        "players": players,
        "lineup": [p["id"] for p in players[:11]],
        "bench": [p["id"] for p in players[11:]],
        "spots": {p["id"]: [u, v] for p, (_, u, v) in zip(players, spots, strict=False)},
    }


def build_metadata(seed: int) -> dict[str, Any]:
    rng = random.Random(f"meta-{seed}")
    used: set[str] = set()
    home = _club(rng, CLUBS[0], used)
    away = _club(rng, CLUBS[1], used)
    venue, city, capacity = VENUES[0]
    kickoff = datetime(2026, 8, 15, 14, 0, tzinfo=UTC) + timedelta(weeks=rng.randint(0, 30))
    return {
        "match_id": f"syn-{seed}",
        "seed": seed,
        "competition": "Synthetic League",
        "season": "2026-27",
        "matchday": rng.randint(1, 38),
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "venue": {"name": venue, "city": city, "capacity": capacity},
        "conditions": {
            "weather": rng.choice(WEATHER),
            "temperature_c": rng.randint(4, 24),
            "wind_kmh": rng.randint(0, 30),
        },
        "referee": {
            "id": "REF-01",
            "name": rng.choice(REFEREE_NAMES),
            "strictness": round(rng.uniform(0.3, 0.8), 2),
        },
        "home_team_id": home["id"],
        "away_team_id": away["id"],
        "teams": [home, away],
    }
