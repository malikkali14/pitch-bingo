"""Masks and hold-backs (spec 4.9).

Each square masks its tags while its window runs; first-to-happen squares mask from kickoff,
so a stat going hidden never signals the event. A feed entry posted while any of its tags is
masked is held back, and revealed once no mask covers it.
"""

import copy
from typing import Any

CLUB_FIELDS = {
    "cards": ("yellow_cards", "red_cards"),
    "fouls": ("fouls",),
    "corners": ("corners",),
    "shots": ("shots", "shots_on_target", "xg"),
    "offsides": ("offsides",),
    "possession": ("possession",),
}
PLAYER_FIELDS = {"shots": ("shots", "xg")}


class Masks:
    def __init__(self) -> None:
        self.by_square: dict[str, set[str]] = {}
        self.held: list[tuple[str, set[str]]] = []

    def tags(self) -> set[str]:
        return set().union(*self.by_square.values()) if self.by_square else set()

    def on(self, square_id: str, tags: list[str]) -> None:
        if tags:
            self.by_square[square_id] = set(tags)

    def off(self, square_id: str) -> list[str]:
        """Lift a square's mask; returns the held entry ids no mask covers any more."""
        self.by_square.pop(square_id, None)
        active = self.tags()
        released = [entry for entry, tags in self.held if not tags & active]
        self.held = [(entry, tags) for entry, tags in self.held if tags & active]
        return released

    def hold(self, entry_id: str, tags: list[str]) -> bool:
        masked = set(tags) & self.tags()
        if masked:
            self.held.append((entry_id, set(tags)))
        return bool(masked)

    def redact(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """A copy of a stats snapshot with masked values set to None (shown as "Hidden")."""
        active = self.tags()
        out = copy.deepcopy(snapshot)
        out["masked"] = sorted(active)
        for tag in active:
            for club in out.get("clubs", {}).values():
                for key in CLUB_FIELDS.get(tag, ()):
                    if key in club:
                        club[key] = None
            for player in out.get("players", {}).values():
                for key in PLAYER_FIELDS.get(tag, ()):
                    if key in player:
                        player[key] = None
        if "possession" in active:
            for pressure in out.get("patterns", {}).get("pressure", {}).values():
                pressure["field_tilt"] = None
        return out
