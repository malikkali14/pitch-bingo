"""The narrator and the agent runner, with a fake client (spec 8.6, 8.7, 8.10, 12.1)."""

import json
from typing import Any

from factories import HOME, Log, load_meta

from app.agents import narrator
from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.agents.orchestrator import Orchestrator
from app.game.card import Profile

META = load_meta()
NAMES = narrator.Names(META)
STRIKER = next(p for p in META["teams"][0]["players"] if p["position"] == "ST")
STATS = {
    "score": {"NBA": 1, "KVL": 0},
    "clubs": {"NBA": {"possession": 58.2, "shots": 4, "shots_on_target": 2, "xg": 0.71,
                      "fouls": None, "corners": 3},
              "KVL": {"possession": 41.8, "shots": 1, "shots_on_target": 0, "xg": 0.1,
                      "fouls": None, "corners": 0}},
    "patterns": {"chaos": {"value": 63.0, "in_control": "NBA"},
                 "momentum": {"value": 41.2},
                 "rhythm": {"tempo": "Frantic"},
                 "pressure": {"NBA": {"ppda": 6.1, "high_regains_5min": 3, "field_tilt": 60}}},
}


def shot_event() -> dict[str, Any]:
    return Log().add("shot", 625.0, team=HOME, player=STRIKER["id"], outcome="saved",
                     tags=("shots",), shot_type="open_play", body_part="right_foot",
                     ball_speed_kmh=101.4, goal_y=33.0, goal_z=1.2, clock="10:25")


def narrator_calls(fake: FakeChatClient) -> list[Any]:
    return [c for c in fake.calls if "explain football moments" in c.instructions]


def insight(headline: str, why: str = "") -> str:
    return json.dumps({"moment_id": "e000001", "headline_facts": [headline],
                       "why_facts": [why] if why else [], "tags": [], "evidence_ids": [],
                       "numbers": []})


def orchestrator(replies: Any, mode: str = "normal") -> tuple[Orchestrator, list, FakeChatClient]:
    fake = FakeChatClient(replies)
    published: list[dict[str, Any]] = []
    orch = Orchestrator(ChatClients(fake, fake, "fake", "fake"), META,
                        lambda: Profile(mode=mode), published.append)
    return orch, published, fake


def test_moment_uses_names_and_hides_masked_stats():
    moment = narrator.build_moment(shot_event(), 72, STATS, [{"pattern": "chaos",
                                   "kind": "chaos_high", "t": 600.0, "team_id": "NBA",
                                   "value": 63.0}], [], NAMES, shot_xg=0.234)
    assert moment["event"]["player"] == STRIKER["full_name"]
    assert moment["event"]["club"] == "Northbridge" and moment["event"]["xg"] == 0.23
    assert moment["score"] == {"Northbridge": 1, "Kestrel": 0}
    assert "fouls" not in moment["stats"]["Northbridge"]          # masked, so left out
    assert moment["pattern_triggers"] == [{"pattern": "chaos", "kind": "chaos_high",
                                           "club": "Northbridge", "value": 63.0}]
    assert "625" not in json.dumps(moment) and "x" not in moment["event"]


def test_a_foul_names_the_fouling_club():
    foul = Log().add("foul", 620.0, team="KVL", player="KVL-04", tags=("fouls",),
                     fouled_id=STRIKER["id"], severity=0.3, advantage=True)
    event = narrator.build_moment(foul, 45, STATS, [], [], NAMES)["event"]
    assert event["fouling_club"] == "Kestrel" and "club" not in event
    assert event["fouled"] == STRIKER["full_name"]


def test_which_events_get_a_line():
    assert narrator.wants_line(40, []) and narrator.wants_line(10, [{"pattern": "chaos"}])
    assert not narrator.wants_line(39, [])


def test_render_fits_the_mode():
    i = narrator.Insight.model_validate_json(insight("A" * 100, "B" * 60))
    assert narrator.render(i, 220) == "A" * 100 + " " + "B" * 60
    assert narrator.render(i, 140) == "A" * 100
    assert narrator.render(i, 50) is None


def run_moment(orch: Orchestrator, significance: int = 72, held: bool = False) -> None:
    orch.on_event(shot_event(), significance, [], [], lambda: STATS, held, shot_xg=0.234)


async def test_a_valid_insight_replaces_the_template_line():
    surname = STRIKER["surname"]
    orch, published, fake = orchestrator([insight(f"{surname} tests the keeper at 101 km/h.",
                                                  "Northbridge have 4 shots to 1.")])
    run_moment(orch)
    await orch.drain()
    assert published == [{"type": "feed.replace", "entry_id": "e000001",
                          "text": f"{surname} tests the keeper at 101 km/h. Northbridge have 4 "
                                  "shots to 1.", "ai": True, "clock": "10:25",
                          "event_type": "shot", "held": False}]
    call = narrator_calls(fake)[0]
    assert "Use ONLY the facts and numbers in INPUT" in call.instructions
    assert call.prompt.startswith("Length: headline_facts[0] must be under 140 characters")
    assert "\nINPUT: {" in call.prompt
    assert orch.health()["narrator"]["ai"] == 1


async def test_an_invented_number_is_retried_with_the_errors():
    orch, published, fake = orchestrator([insight("A 115 km/h strike."),
                                          insight("A 101 km/h strike.")])
    run_moment(orch)
    await orch.drain()
    assert published[0]["text"] == "A 101 km/h strike."
    calls = narrator_calls(fake)
    assert len(calls) == 2
    assert "the number 115 isn't in the input" in calls[1].prompt


async def test_two_bad_answers_keep_the_template():
    orch, published, fake = orchestrator([insight("Zlatanovic scores 7.")])
    run_moment(orch)
    await orch.drain()
    assert published == [] and len(narrator_calls(fake)) == 2
    health = orch.health()["narrator"]
    assert health["verifier_failures"] == 1 and health["fallbacks"] == 1


async def test_invalid_json_then_valid():
    orch, published, fake = orchestrator(["not json", insight("A save from close range.")])
    run_moment(orch)
    await orch.drain()
    assert published[0]["text"] == "A save from close range."
    assert "not valid JSON" in narrator_calls(fake)[1].prompt


async def test_an_error_keeps_the_template():
    orch, published, fake = orchestrator([RuntimeError("401 Unauthorized")])
    run_moment(orch)
    await orch.drain()
    assert published == [] and orch.health()["narrator"]["errors"] == 1


async def test_quiet_moments_and_offline_make_no_calls():
    orch, published, fake = orchestrator([insight("x")])
    run_moment(orch, significance=20)
    await orch.drain()
    assert fake.calls == []
    offline = Orchestrator(None, META, lambda: Profile(), published.append)
    run_moment(offline)
    await offline.drain()
    assert published == []


async def test_held_lines_say_so():
    orch, published, fake = orchestrator([insight("A save from close range.")])
    run_moment(orch, held=True)
    await orch.drain()
    assert published[0]["held"] is True


async def test_too_many_at_once_keep_their_templates():
    orch, published, fake = orchestrator([insight("A save from close range.")])
    for _ in range(5):
        run_moment(orch)
    await orch.drain()
    assert len(published) == 3 and orch.health()["narrator"]["skipped"] == 2
