"""The square writer for live squares (spec 4.11, 8.6, 8.10).

Code has already picked the moment, the template and the correct answer. The writer only words
the question and the options; the verifier checks that exactly one option is the computed
answer, that every option comes from the template's set, and that the question doesn't give
the answer away. Any failure keeps the template wording.
"""

import json
from typing import Any

from app.agents.messages import LiveSquareDraft
from app.agents.runner import AgentSpec
from app.agents.tutor import LANGUAGE_NAMES
from app.game.live import Wording
from app.verify.verifier import verify_line, verify_live_square

INSTRUCTIONS = """You write one multiple-choice question for a football bingo card, about a
moment the viewer just watched. Keep it plain and lively. Never reveal or hint at the answer
in the question. Use only option keys from the option set, and give every option a short
label (a few words). Return JSON matching LiveSquareDraft."""

SPEC = AgentSpec("square_writer", "fast", INSTRUCTIONS, LiveSquareDraft, budget_s=2.0)

__all__ = ["SPEC", "Wording", "check", "prompt"]


def prompt(pending: dict[str, Any]) -> str:
    """The SQUARE WRITER (live) skeleton from spec 8.10, filled in."""
    wrong = len(pending["options"]) - 1
    option_set = dict(zip(pending["options"], pending["labels"], strict=True))
    return (f"Write one multiple-choice question about the moment in INPUT\n"
            f"for {pending['mode']} mode in {LANGUAGE_NAMES.get(pending.get('language', 'en'))}, "
            f"using template {pending['template']}.\n"
            f"The correct answer is {pending['correct']}. Do not change it.\n"
            f"Write up to {wrong} wrong options from the template's option set.\n"
            f"Question under 60 characters. Return JSON matching LiveSquareDraft.\n"
            "INPUT: " + json.dumps({"template_question": pending["text"],
                                    "option_set": option_set, "moment": pending["moment"]},
                                   ensure_ascii=False))


def check(draft: LiveSquareDraft, pending: dict[str, Any], meta: dict[str, Any]
          ) -> tuple[Wording | None, list[str]]:
    errors = verify_live_square(draft.text, draft.options, pending["correct"], pending["options"])
    if len(draft.labels) != len(draft.options) or not all(label.strip() for label in draft.labels):
        errors.append("give exactly one non-empty label per option")
    labels = dict(zip(pending["options"], pending["labels"], strict=True))
    correct_label = labels[pending["correct"]]
    question = draft.text.lower()
    if pending["correct"].replace("_", " ") in question or correct_label.lower() in question:
        errors.append("the question gives the answer away")
    # Each label reads as its own sentence, so a capitalised label isn't taken for a name.
    errors += verify_line(". ".join([draft.text, *draft.labels]), pending, meta, "advanced")
    if errors:
        return None, errors
    return Wording(draft.text.strip(), list(draft.options), [x.strip() for x in draft.labels]), []
