"""The square writer (spec 4.11, 8.6, 8.10): LLM wording for live squares, while the correct
answer stays computed by code."""

import json
from typing import Any

from factories import HOME, Log, load_meta
from game_helpers import FakeTime, of

from app.agents import square_writer
from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.agents.orchestrator import Orchestrator
from app.game.card import Profile
from app.game.game import Game

META = load_meta()


def deferred_game(mode: str = "normal") -> tuple[Game, Log]:
    clock = FakeTime()
    game = Game(META, Profile.parse({"mode": mode}, META), now=clock.now, wall_ms=clock.wall_ms,
                defer_live=True)
    log = Log()
    game.on_event(log.add("period_start", 0.0, team=None))
    return game, log


def offside(game: Game, log: Log) -> list[dict[str, Any]]:
    log.pass_(598.0, HOME, "NBA-08", outcome="offside", pass_type="through_ball", length_m=31.0)
    game.on_event(log.events[-1])
    return game.on_event(log.add("offside", 600.0, team=HOME, player="NBA-09",
                                 tags=("offsides",)), significance=60)


def test_the_game_holds_a_live_square_until_its_wording_arrives():
    game, log = deferred_game()
    out = offside(game, log)
    pending = of(out, "live.pending")[0]
    assert not of(out, "square.added") and not of(out, "square.window_open")
    assert pending["correct"] == "offside" and pending["template"] == "referee"
    # Its masks go on now, so the call's own feed line is held back.
    assert of(out, "mask.on")[0]["tags"] == ["fouls", "offsides"]
    assert game.hold(log.events[-1])
    sq = game.board.get(pending["square_id"])
    assert sq.state == "waiting" and sq.view()["state"] == "waiting"

    out = game.open_live(pending["square_id"], square_writer.Wording(
        "What did the ref call on that run?", ["foul", "offside", "advantage"],
        ["Foul", "Offside", "Played on"]))
    added = of(out, "square.added")[0]["square"]
    assert added["text"]["en"] == "What did the ref call on that run?"
    assert added["options"] == ["foul", "offside", "advantage"]
    assert added["option_labels"]["en"] == ["Foul", "Offside", "Played on"]
    assert of(out, "square.window_open")
    assert game.board.get(added["id"]).correct_answer == "offside"     # still from code


def test_without_wording_the_template_opens():
    game, log = deferred_game()
    pending = of(offside(game, log), "live.pending")[0]
    added = of(game.open_live(pending["square_id"], None), "square.added")[0]["square"]
    assert added["text"]["en"] == "What did the referee just give?"
    assert added["options"] == ["foul", "offside", "advantage", "no_call"]


PENDING = {"square_id": "bl_1", "template": "referee", "mode": "normal",
           "text": "What did the referee just give?",
           "options": ["foul", "offside", "advantage", "no_call"],
           "labels": ["Foul", "Offside", "Advantage played", "No call"], "correct": "offside",
           "moment": {"call": "offside", "clock": "10:00", "club": "Northbridge"}}


def draft(text: str, options: list[str], labels: list[str] | None = None) -> str:
    return json.dumps({"text": text, "options": options,
                       "labels": labels or [o.title() for o in options]})


def check(reply: str) -> list[str]:
    value = square_writer.SPEC.output.model_validate_json(reply)
    return square_writer.check(value, PENDING, META)[1]


def test_a_good_draft_passes():
    assert check(draft("What was the call on that through ball?",
                       ["foul", "offside", "advantage"])) == []


def test_drafts_that_move_the_answer_fail():
    assert check(draft("What was the call?", ["foul", "advantage"]))            # answer dropped
    assert check(draft("What was the call?", ["offside", "offside", "foul"]))   # twice
    assert check(draft("What was the call?", ["offside", "corner"]))            # not the set


def test_a_question_that_gives_the_answer_away_fails():
    errors = check(draft("Was that offside or a foul?", ["foul", "offside"]))
    assert any("gives the answer away" in e for e in errors)


def test_labels_must_match_the_options():
    errors = check(draft("What was the call?", ["foul", "offside"], ["Foul"]))
    assert any("label" in e for e in errors)


def test_capitalised_labels_are_not_names():
    assert check(draft("What was the call?", ["foul", "offside", "advantage"],
                       ["Foul", "Offside", "Play on"])) == []


def test_long_questions_fail():
    assert check(draft("Q" * 61 + "?", ["foul", "offside"]))


async def test_the_orchestrator_words_a_square_or_falls_back():
    fake = FakeChatClient([draft("What was the call on that run?", ["foul", "offside"]),
                           "nonsense", "nonsense"])
    orch = Orchestrator(ChatClients(fake, fake, "f", "f"), META, lambda: Profile(), lambda m: None)
    got: list[Any] = []
    orch.write_square(PENDING, got.append)
    await orch.drain()
    assert got[0].text == "What was the call on that run?"
    assert "The correct answer is offside. Do not change it." in fake.calls[0].prompt
    orch.write_square(PENDING, got.append)
    await orch.drain()
    assert got[1] is None
    offline = Orchestrator(None, META, lambda: Profile(), lambda m: None)
    offline.write_square(PENDING, got.append)
    assert got[2] is None                                               # at once, no task
