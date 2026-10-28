"""The strategist's one-line reason (spec 4.12, 8.6). The moves stay the optimizer's."""

import json
from typing import Any

from factories import load_meta

from app.agents import strategist_reason
from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.agents.orchestrator import Orchestrator
from app.game.card import Profile, build_card

META = load_meta()
BOARD = build_card(META, Profile())
for cell in ((1, 0), (1, 1), (1, 3)):
    BOARD.at(cell).state = "correct"
ADVICE = {"type": "strategy.advice", "advice_id": "a1", "before": 0.31, "after": 0.47,
          "reason": "Moved a blank into row 2: 3 of its 5 squares are already correct.",
          "applied": False,
          "moves": [{"from_cell": {"row": 0, "col": 0}, "to_cell": {"row": 1, "col": 2}}]}


def test_input_describes_the_move_and_its_line():
    payload = strategist_reason.build_input(ADVICE, BOARD.view())
    assert payload["chance_before_pct"] == 31 and payload["chance_after_pct"] == 47
    assert payload["moves"] == [{"from": "row 1, column 1", "to": "row 2, column 3"}]
    line = payload["lines"][0]
    assert line["line"] == "row 2" and line["correct"] == 3 and len(line["squares"]) == 5
    assert payload["fallback_reason"] == ADVICE["reason"]


def check(reason: str) -> list[str]:
    payload = strategist_reason.build_input(ADVICE, BOARD.view())
    value = strategist_reason.SPEC.output.model_validate_json(json.dumps({"reason": reason}))
    return strategist_reason.check(value, payload, META)[1]


def test_a_grounded_reason_passes():
    assert check("Row 2 has 3 correct already; the blank fills its gap and lifts you to 47%.") == []


def test_invented_numbers_and_long_reasons_fail():
    assert check("Row 2 has 4 correct already.")
    assert any("120" in e for e in check("x" * 121))


async def run(replies: Any) -> list[dict[str, Any]]:
    fake = FakeChatClient(replies)
    orch = Orchestrator(ChatClients(fake, fake, "f", "f"), META, lambda: Profile(), lambda m: None)
    got: list[dict[str, Any]] = []
    orch.explain_advice(ADVICE, BOARD.view(), got.append)
    await orch.drain()
    return got


async def test_the_orchestrator_rewrites_the_reason():
    got = await run([json.dumps({"reason": "Row 2 has 3 correct: this blank fills the gap."})])
    assert got == [{**ADVICE, "reason": "Row 2 has 3 correct: this blank fills the gap."}]


async def test_a_bad_reason_keeps_the_template():
    got = await run([json.dumps({"reason": "Row 2 has 9 correct."})])
    assert got == [ADVICE]


async def test_offline_sends_the_template_at_once():
    orch = Orchestrator(None, META, lambda: Profile(), lambda m: None)
    got: list[dict[str, Any]] = []
    orch.explain_advice(ADVICE, BOARD.view(), got.append)
    assert got == [ADVICE]
