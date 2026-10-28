"""The strategist's reason (spec 4.12, 8.6): one line on why the optimizer chose its move.

The optimizer (game/strategist.py) picks the moves in code; this agent only explains them.
Its input is the move, the chance of a line before and after, and the lines the moved square
lands in, so the reason can name what is already correct there and what is still to come.
"""

from typing import Any

from app.agents.messages import StrategyReason
from app.agents.runner import AgentSpec
from app.game.card import LINES
from app.verify.verifier import verify_line

LIMIT = 120
PROMPT = """You coach a football bingo player. Explain in one line, under 120 characters, why
the suggested move helps them complete a line. Use only facts and numbers from INPUT: name the
line, what is already correct in it, or what is still to come. Plain words, no betting language.
Return JSON matching the StrategyReason schema."""

SPEC = AgentSpec("strategist", "fast", PROMPT, StrategyReason, budget_s=3.0)
GOOD = {"correct", "void", "wildcard"}


def _cell_name(cell: dict[str, int]) -> str:
    return f"row {cell['row'] + 1}, column {cell['col'] + 1}"


def _line_name(line: str) -> str:
    kind, n = line.split(":")
    if kind == "diag":
        return "the diagonal" if n == "0" else "the other diagonal"
    return f"{'row' if kind == 'row' else 'column'} {int(n) + 1}"


def build_input(advice: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    by_cell = {(s["cell"]["row"], s["cell"]["col"]): s for s in board["squares"]}
    for move in advice["moves"]:            # the board as it is after the moves
        a = (move["from_cell"]["row"], move["from_cell"]["col"])
        b = (move["to_cell"]["row"], move["to_cell"]["col"])
        by_cell[a], by_cell[b] = by_cell[b], by_cell[a]
    landing = advice["moves"][0]["to_cell"]
    lines = []
    for line, cells in LINES.items():
        if (landing["row"], landing["col"]) not in cells or line in board["scored_lines"]:
            continue
        squares = [by_cell[c] for c in cells]
        lines.append({
            "line": _line_name(line),
            "correct": sum(s["state"] in GOOD for s in squares),
            "squares": [{"question": s["text"].get("en") or "empty blank", "state": s["state"],
                         **({"at": f"{s['deadline_s'] // 60}'"} if s.get("deadline_s") else {})}
                        for s in squares],
        })
    return {
        "moves": [{"from": _cell_name(m["from_cell"]), "to": _cell_name(m["to_cell"])}
                  for m in advice["moves"]],
        "chance_before_pct": round(advice["before"] * 100),
        "chance_after_pct": round(advice["after"] * 100),
        "lines": sorted(lines, key=lambda x: -x["correct"]),
        "fallback_reason": advice["reason"],
    }


def check(value: StrategyReason, payload: dict[str, Any], meta: dict[str, Any]
          ) -> tuple[str | None, list[str]]:
    reason = value.reason.strip()
    errors = verify_line(reason, payload, meta, "normal")
    if len(reason) > LIMIT:
        errors.append(f"the reason must be under {LIMIT} characters")
    return (None, errors) if errors else (reason, [])
