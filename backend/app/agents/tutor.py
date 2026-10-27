"""Explanations when a window closes (spec 5.1, 8.4 window-close workflow, 8.6).

Normal mode: the rules tutor (quality model) explains the call or rule in one or two lines a
new fan understands, from a stored rule summary. Advanced mode: the narrator's voice adds the
tactical context (fast model). Either way the template explanation has already posted, and
this replaces it only if it passes the verifier.
"""

from typing import Any

from app.agents.messages import Explanation
from app.agents.runner import AgentSpec
from app.verify.verifier import verify_line

# The calls and rules the dots can show (spec 8.6), in our own words.
RULES = {
    "foul": "A foul is an unfair challenge, like a trip, push or late tackle. The other side "
            "gets a free kick from where it happened.",
    "advantage": "If stopping play would help the side that was fouled, the referee lets it "
                 "carry on. That is playing advantage; the foul can still be punished later.",
    "offside": "A player is offside if, when a team-mate passes, they are nearer the goal line "
               "than both the ball and the second-last defender, in the opponents' half. Being "
               "level with that defender is onside. The defending side gets a free kick.",
    "corner": "When the defending side last touches the ball before it crosses their own goal "
              "line, the attackers take a corner from the corner flag.",
    "goal_kick": "When the attacking side last touches the ball before it crosses the goal line "
                 "without a goal, the defenders restart with a goal kick.",
    "throw_in": "When the ball crosses a touchline, the side that didn't touch it last throws it "
                "back in with both hands, from behind the head.",
    "yellow_card": "A yellow card is a caution for reckless fouls, time wasting or dissent. Two "
                   "in one match make a red.",
    "red_card": "A red card sends a player off for the rest of the match, and the team plays on "
                "with one fewer. It comes from a second yellow or a serious offence.",
    "free_kick": "A free kick restarts play after a foul or an offside; opponents must stand "
                 "at least 9.15 metres away.",
    "substitution": "Each side can change players during stoppages. A player taken off can't "
                    "come back on.",
    "goal": "A goal counts when the whole ball crosses the goal line between the posts and "
            "under the bar. The side that conceded kicks off.",
    "shot_on_target": "A shot on target would have gone in without the keeper or a last "
                      "defender. Saves and goals count; shots wide or blocked don't.",
    "possession": "Possession is the share of time each side has the ball while it is in play.",
    "xg": "Expected goals (xG) is the chance a shot becomes a goal, from where and how it was "
          "taken. 0.10 means about one in ten such shots go in.",
    "pass": "Long passes skip lines of opponents but are harder to complete; short ones keep the "
            "ball safely.",
    "shot_speed": "Shot speed is how fast the ball leaves the boot. Over 100 km/h gives a keeper "
                  "little time to react.",
    "build_up": "A long passing move pulls defenders out of shape before the final pass or shot.",
}

TEMPLATE_RULES = {
    "yellow_cards": "yellow_card", "first_booking": "yellow_card", "corners": "corner",
    "first_corner": "corner", "offsides": "offside", "first_offside": "offside",
    "first_foul": "foul", "club_fouls": "foul", "first_free_kick": "free_kick",
    "subs": "substitution", "first_sub_off": "substitution", "goal": "goal",
    "first_goal": "goal", "more_shots": "shot_on_target", "first_shot": "shot_on_target",
    "first_on_target": "shot_on_target", "focus_shot": "shot_on_target",
    "possession": "possession", "first_throw_in": "throw_in", "throw_team": "throw_in",
    "shot_xg": "xg", "shot_speed": "shot_speed", "pass_length": "pass",
    "move_passes": "build_up",
}

TUTOR_PROMPT = """You are a friendly rules tutor for new football fans watching a live match.
In one or two short sentences, explain the call or rule behind the bingo square in INPUT,
using the rule summary and the incident. Plain words, no jargon. Use only facts and numbers
from INPUT. No betting language. Return JSON matching the Explanation schema."""

CONTEXT_PROMPT = """You add tactical context for a knowledgeable football fan. In one or two
short sentences, say what the moment behind the bingo square in INPUT tells us about the
match: how it came about and what it means. Use only facts and numbers from INPUT. No betting
language. Return JSON matching the Explanation schema."""

TUTOR = AgentSpec("rules_tutor", "quality", TUTOR_PROMPT, Explanation, budget_s=3.0)
CONTEXT = AgentSpec("narrator_context", "fast", CONTEXT_PROMPT, Explanation, budget_s=2.0)


def rule_for(template: str, answer: str | None) -> str | None:
    """The rule a square is about. Referee and restart squares depend on the answer."""
    if template == "referee":
        return answer if answer in RULES else "foul"
    if template == "restart":
        return answer if answer in RULES else None
    return TEMPLATE_RULES.get(template)


def build_input(square: dict[str, Any]) -> dict[str, Any]:
    """square: question, kind, template, answer (label), answer key, result, clock, events."""
    rule = rule_for(square["template"], square.get("answer_key", square.get("answer", "")
                                                   .lower().replace("-", "_").replace(" ", "_")))
    payload: dict[str, Any] = {k: square[k] for k in ("square_id", "question", "kind", "answer", "result",
                                      "clock", "events") if k in square}
    if rule:
        payload["rule"] = {"call": rule, "summary": RULES[rule]}
    return payload


def check(value: Explanation, payload: dict[str, Any], meta: dict[str, Any], mode: str
          ) -> tuple[str | None, list[str]]:
    text = value.text.strip()
    errors = verify_line(text, payload, meta, mode)
    return (None, errors) if errors else (text, [])
