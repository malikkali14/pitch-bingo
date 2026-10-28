"""The personalizer (spec 5.7, 8.6): one insight, rendered once per profile type.

It writes the final line in the profile's mode and language, leading with the viewer's club
or focus player when the moment involves them. Lines are cached by match, moment and a hash
of the profile fields that change the wording, so viewers who share a profile type share one
LLM call: the scaling story in 5.7. If it fails, the insight's plain rendering is used.
"""

import hashlib
import json
from collections import OrderedDict
from typing import Any

from app.agents.messages import Insight, RenderedLine
from app.agents.runner import AgentSpec
from app.game.card import Profile
from app.verify.verifier import LIMITS, verify_line

PROMPT = """You turn a football insight into one feed line for a particular viewer.
Write directly in the profile's language. Normal mode: plain words, under 140 characters.
Advanced mode: tactical terms allowed, under 220 characters. When the insight involves the
viewer's favorite club or focus player, lead with them, honestly, including bad news, and never
mock the other club. When it touches the viewer's my_metric, lead with that stat. Never add a
number or a name that isn't in INPUT. No betting language.
Return JSON matching the RenderedLine schema, copying moment_id."""

SPEC = AgentSpec("personalizer", "fast", PROMPT, RenderedLine, budget_s=2.0)
CACHE_SIZE = 5000
CACHE: OrderedDict[tuple[str, str, str], str] = OrderedDict()


def profile_hash(profile: Profile) -> str:
    """Only the fields that change a line: not the handle or the strategist setting."""
    used = {"mode": profile.mode, "club": profile.club, "focus": profile.focus_player_id,
            "language": profile.language, "units": profile.units, "metric": profile.my_metric}
    return hashlib.sha1(json.dumps(used, sort_keys=True).encode()).hexdigest()[:12]


def cached(key: tuple[str, str, str]) -> str | None:
    if key in CACHE:
        CACHE.move_to_end(key)
        return CACHE[key]
    return None


def remember(key: tuple[str, str, str], text: str) -> None:
    CACHE[key] = text
    CACHE.move_to_end(key)
    while len(CACHE) > CACHE_SIZE:
        CACHE.popitem(last=False)


def build_input(insight: Insight, profile: Profile, names: Any,
                moment: dict[str, Any] | None = None) -> dict[str, Any]:
    viewer = {"mode": profile.mode, "language": profile.language, "units": profile.units}
    if profile.club:
        viewer["favorite_club"] = names.club(profile.club)
    if profile.focus_player_id:
        viewer["focus_player"] = names.player(profile.focus_player_id)
    if profile.my_metric:
        viewer["my_metric"] = profile.my_metric
    payload = {"insight": insight.model_dump(exclude={"evidence_ids", "tags"}), "profile": viewer}
    event = (moment or {}).get("event", {})
    imperial = {k: v for k, v in event.items() if k.endswith(("_mph", "_yd"))}
    if profile.units == "imperial" and imperial:
        payload["imperial"] = imperial              # added by code (narrator.add_imperial)
    return payload


def unit_rule(profile: Profile) -> str:
    """Imperial viewers get mph and yards, which code has already added to the moment."""
    if profile.units != "imperial":
        return ""
    return ("\nUnits: this viewer reads mph and yards. Use the _mph and _yd values in INPUT, "
            "never km/h or metres.")


def check(value: RenderedLine, moment: dict[str, Any], payload: dict[str, Any],
          meta: dict[str, Any], mode: str) -> tuple[str | None, list[str]]:
    """Numbers and names are checked against the original moment, which is grounded, and the
    viewer's own club and player names."""
    text = value.text.strip()
    errors = verify_line(text, {"moment": moment, "profile": payload["profile"]}, meta, mode)
    if len(text) > LIMITS[mode]:
        errors.append(f"keep it under {LIMITS[mode]} characters")
    return (None, errors) if errors else (text, [])
