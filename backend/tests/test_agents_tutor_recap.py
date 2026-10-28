"""Rules tutor (fast model) and recap (quality model) (spec 5.1, 8.2, 8.4, 8.6)."""

import json
from typing import Any

from factories import load_meta

from app.agents import recap, tutor
from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.agents.orchestrator import Orchestrator
from app.game.card import Profile

META = load_meta()
PLAYER = next(p for p in META["teams"][0]["players"] if p["id"] == "NBA-09")
FULL, SURNAME = PLAYER["full_name"], PLAYER["surname"]
OFFSIDE = {"square_id": "bl_1", "question": "What did the referee just give?", "kind": "live",
           "template": "referee", "answer": "Offside", "result": "correct", "clock": "33:23",
           "events": [{"type": "pass", "clock": "33:20", "player": FULL,
                       "club": "Northbridge", "pass_type": "through_ball", "outcome": "offside"},
                      {"type": "offside", "clock": "33:23", "player": FULL,
                       "club": "Northbridge"}],
           "template_text": "What did the referee just give? Answer: Offside."}


def orch(replies: Any, mode: str = "normal") -> tuple[Orchestrator, FakeChatClient,
                                                      FakeChatClient, list[dict[str, Any]]]:
    fast, quality = FakeChatClient(replies), FakeChatClient(replies)
    published: list[dict[str, Any]] = []
    o = Orchestrator(ChatClients(fast, quality, "f", "q"), META, lambda: Profile(mode=mode),
                     published.append)
    return o, fast, quality, published


def test_tutor_input_carries_the_rule():
    payload = tutor.build_input(OFFSIDE)
    assert payload["rule"]["call"] == "offside"
    assert "level with" in payload["rule"]["summary"]
    assert tutor.rule_for("first_free_kick", "KVL") == "free_kick"
    assert tutor.rule_for("restart", "goal_kick") == "goal_kick"
    assert len(tutor.RULES) >= 15


async def test_normal_mode_explanations_come_from_the_tutor_on_the_fast_model():
    line = f"{SURNAME} was beyond the last defender when the ball was played, so offside."
    o, fast, quality, published = orch([json.dumps({"square_id": "bl_1", "text": line})])
    o.explain_square(OFFSIDE)
    await o.drain()
    assert published == [{"type": "square.explanation", "square_id": "bl_1", "text": line,
                          "ai": True}]
    assert fast.calls and not quality.calls
    assert "level with" in fast.calls[0].prompt
    assert fast.calls[0].prompt.startswith("Length: the text must be under 140 characters")


async def test_advanced_mode_explanations_add_tactics_on_the_fast_model():
    line = f"Northbridge went long with a through ball and {SURNAME} timed it badly."
    o, fast, quality, published = orch([json.dumps({"square_id": "bl_1", "text": line})],
                                       mode="advanced")
    o.explain_square(OFFSIDE)
    await o.drain()
    assert published[0]["text"] == line and fast.calls and not quality.calls


async def test_a_bad_explanation_keeps_the_template():
    o, fast, quality, published = orch([json.dumps({"square_id": "bl_1",
                                                    "text": "Offside after 3 passes."})])
    o.explain_square(OFFSIDE)
    await o.drain()
    assert published == []


SUMMARY = recap.Summary(
    kind="halftime", score={"Northbridge": 1, "Kestrel": 0},
    goals=[{"minute": "15'", "scorer": FULL, "club": "Northbridge"}],
    stats={"Northbridge": {"possession": 58.2, "shots": 7, "xg": 0.91},
           "Kestrel": {"possession": 41.8, "shots": 3, "xg": 0.32}},
    moments=[f"15' {SURNAME} scores from close range."],
    patterns=["Northbridge in control for long spells."],
    standout={"player": FULL, "club": "Northbridge", "touches": 31},
    card={"points": 640, "correct": 5, "lines": 0, "rank": 4, "of": 21},
    club="Northbridge", focus=None)


def test_template_recap_from_the_summary():
    r = recap.template(SUMMARY)
    assert r.kind == "halftime" and not r.ai
    assert r.content.headline == "Half-time: Northbridge 1–0 Kestrel"
    text = " ".join(r.text_parts())
    assert SURNAME in text and "58%" in text and "640 points" in text
    assert len(r.content.talking_points) == 3


def good_recap(**extra: Any) -> str:
    return json.dumps({"headline": f"{SURNAME}'s goal splits the sides at the break",
                       "paragraphs": [f"{FULL} scored on 15' for Northbridge.",
                                      "Northbridge had 58% of the ball and 7 shots to 3."],
                       "talking_points": [f"{SURNAME}'s finish", "Northbridge's control",
                                          "Kestrel's 3 shots"], "club_paragraph": None,
                       "player_paragraph": None, "bingo_summary": None, **extra})


async def test_recap_from_the_quality_model():
    o, fast, quality, published = orch([good_recap()])
    o.write_recap(SUMMARY)
    await o.drain()
    kinds = [(m["kind"], m["ai"]) for m in published]
    assert kinds == [("halftime", False), ("halftime", True)]         # template first
    assert published[1]["content"]["headline"].startswith(SURNAME)
    assert quality.calls and not fast.calls


async def test_a_recap_with_an_invented_fact_keeps_the_template():
    o, fast, quality, published = orch([good_recap(paragraphs=[f"{SURNAME} scored twice by 40'."])])
    o.write_recap(SUMMARY)
    await o.drain()
    assert [m["ai"] for m in published] == [False]


async def test_definitions_send_the_stored_line_then_the_tutors_once_for_everyone():
    from app.agents.orchestrator import DEFINITION_CACHE
    DEFINITION_CACHE.clear()
    o, fast, quality, published = orch([json.dumps({"term": "field tilt",
                                                    "text": "Who is pinning whom back."})])
    assert o.define("field_tilt")
    await o.drain()
    assert [(m["text"], m["ai"]) for m in published] == [
        (tutor.DEFINITIONS["field_tilt"], False), ("Who is pinning whom back.", True)]
    assert fast.calls[0].prompt.startswith("Length: the text must be under 140 characters")
    o2, fast2, _, published2 = orch(["unused"])
    o2.define("field_tilt")
    await o2.drain()
    assert published2 == [{"type": "definition", "term": "field_tilt",
                           "text": "Who is pinning whom back.", "ai": True}] and not fast2.calls
    assert not o2.define("nonsense")
    DEFINITION_CACHE.clear()


def test_every_stat_and_rule_has_a_definition():
    for term in ("possession", "xg", "ppda", "field_tilt", "tempo", "chaos", "momentum", "offside",
                 "corner", "shots", "cards", "pass_accuracy"):
        assert tutor.DEFINITIONS[term]


def test_catch_up_recap_template():
    r = recap.template(recap.Summary(kind="catch_up", score={"Northbridge": 0, "Kestrel": 0}))
    assert r.content.headline == "Catch-up: Northbridge 0–0 Kestrel"
