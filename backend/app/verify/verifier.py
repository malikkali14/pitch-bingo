"""The verifier (spec 8.7): code that checks every LLM output before it reaches the screen.

Numbers: each number in the text must match a number in that agent's input. Counts and
minutes match exactly, percentages to 1 point, decimals under 1 (xG) to 0.01, and other
measures (speeds, distances) to 0.5. "0.15" and "0,15" read the same.
Names: every player or club named must be in the match metadata and in the input, and a
capitalised word that isn't a known name or an ordinary word counts as an invented name.
Timing: words like "half-time", "late on" or "early" must fit the moment's clock.
Plus length limits by mode and a blocklist of betting words.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

LIMITS = {"normal": 140, "advanced": 220}
QUESTION_LIMIT = 60
BETTING = re.compile(r"\b(odds|bets?|betting|wagers?|stakes?)\b", re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(\s*%)?")
WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][\w'’-]*")
# Capitalised words a line may use that are not names.
ORDINARY = {
    "a", "an", "and", "the", "it", "its", "this", "that", "these", "those", "then", "now",
    "but", "so", "still", "yet", "with", "without", "after", "before", "since", "as", "at",
    "in", "on", "of", "for", "from", "to", "by", "up", "down", "into", "out", "over",
    "again", "another", "big", "huge", "great", "what", "who", "how", "why", "when", "where",
    "first", "second", "third", "half", "full", "time", "goal", "goals", "shot", "shots",
    "save", "corner", "foul", "offside", "advantage", "card", "yellow", "red", "penalty",
    "free", "kick", "throw", "pressure", "press", "pressing", "chaos", "control", "calm",
    "chaotic", "momentum", "tempo", "possession", "xg", "ppda", "var", "kick-off", "kickoff",
    "home", "away", "keeper", "goalkeeper", "striker", "defence", "defense", "midfield",
    "he", "she", "they", "their", "his", "her", "we", "you", "your", "our", "no", "yes",
    "not", "only", "just", "every", "all", "both", "one", "two", "three", "four", "five",
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "il", "elle", "ils", "quel",
    "quelle", "encore", "toujours", "après", "avant", "puis", "mais", "carton",
}


# Time words, and the clock minutes (and half) where they make sense.
TIMING = [
    (re.compile(r"\b(half[- ]?time|interval|(before|towards?|near|close to) the break)\b",
                re.IGNORECASE), lambda minute, half, added: half == 1 and (minute >= 40 or added)),
    (re.compile(r"\b(late on|late in the (game|match)|dying (minutes|moments)"
                r"|closing (stages|minutes)|final whistle|stoppage time|added time|injury time"
                r"|full[- ]?time)\b",
                re.IGNORECASE), lambda minute, half, added: minute >= 80 or added),
    (re.compile(r"\b(early|opening (minutes|exchanges|stages))\b", re.IGNORECASE),
     lambda minute, half, added: half == 1 and minute <= 25),
]


@dataclass(frozen=True)
class Number:
    text: str
    value: float
    decimals: bool
    percent: bool


def numbers_in(text: str) -> list[Number]:
    """Numbers as written: "0,15" and "0.15" are both 0.15; "45+2" is 45 and 2."""
    found = []
    for match in NUMBER.finditer(text):
        raw = match.group(1)
        found.append(Number(raw, float(raw.replace(",", ".")), "," in raw or "." in raw,
                            bool(match.group(2))))
    return found


def _source_numbers(source: Any) -> list[float]:
    values: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, int | float):
            values.append(float(node))
        elif isinstance(node, str):
            values.extend(n.value for n in numbers_in(node))
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(key)
                walk(value)
        elif isinstance(node, list | tuple):
            for item in node:
                walk(item)

    walk(source)
    return values


def _matches(number: Number, source: float) -> bool:
    gap = abs(number.value - source)
    if number.percent:
        return gap <= 1.0
    if number.decimals:
        return gap <= (0.01 if number.value < 1 else 0.5) + 1e-9
    if source == int(source):
        return gap < 1e-9                       # counts and minutes: exactly
    return gap <= 0.5 + 1e-9                    # a measure rounded to a whole number


@lru_cache(maxsize=16)
def _known_names(meta_json: str) -> tuple[frozenset[str], frozenset[str]]:
    """(names to look for in text, every word that is part of a known name)."""
    meta = json.loads(meta_json)
    names: set[str] = set()
    for team in meta["teams"]:
        names |= {team["name"], team["short_name"]}
        for player in team["players"]:
            names |= {player["full_name"], player["surname"]}
    parts = {w.lower() for name in names for w in WORD.findall(name)}
    for team in meta["teams"]:
        for player in team["players"]:
            parts |= {w.lower() for w in WORD.findall(player["full_name"])}
    return frozenset(names), frozenset(parts)


def _name_errors(text: str, source_text: str, meta: dict[str, Any]) -> list[str]:
    names, parts = _known_names(json.dumps(meta, sort_keys=True))
    errors = []
    for name in sorted(names, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", text) and name not in source_text:
            errors.append(f"names {name}, who isn't part of this moment")
    for sentence in re.split(r"(?<=[.!?:;])\s+", text):
        words = WORD.findall(sentence)
        for word in words[1:]:                  # the first word is capitalised anyway
            bare = re.sub(r"['’]s$", "", word)
            if bare[:1].isupper() and bare.lower() not in parts and \
                    bare.lower() not in ORDINARY:
                errors.append(f"names {bare}, who isn't in this match")
    return errors


def _clock_of(source: Any) -> tuple[str, int] | None:
    """The moment's clock and half, from the source or a nested moment."""
    if not isinstance(source, dict):
        return None
    node = source if "clock" in source else source.get("moment")
    if not isinstance(node, dict) or not isinstance(node.get("clock"), str):
        return None
    half = node.get("half") or node.get("period") or 1
    return node["clock"], int(half)


def _timing_errors(text: str, source: Any) -> list[str]:
    found = _clock_of(source)
    if found is None:
        return []
    clock, half = found
    minute_part = clock.split(":")[0]
    added = "+" in minute_part
    minute = int(minute_part.split("+")[0])
    errors = []
    for pattern, fits in TIMING:
        match = pattern.search(text)
        if match and not fits(minute, half, added):
            errors.append(f"timing: '{match.group(0)}' doesn't fit the clock {clock}")
    return errors


def verify_line(text: str, source: Any, meta: dict[str, Any], mode: str = "normal"
                ) -> list[str]:
    """Errors in one line of AI text (an empty list means it passes)."""
    errors = []
    stripped = text.strip()
    if not stripped:
        return ["the text is empty"]
    limit = LIMITS.get(mode, LIMITS["normal"])
    if len(stripped) > limit:
        errors.append(f"the text is too long: {len(stripped)} characters, limit {limit}")
    if BETTING.search(stripped):
        errors.append("uses betting language")
    pool = _source_numbers(source)
    for number in numbers_in(stripped):
        if not any(_matches(number, s) for s in pool):
            errors.append(f"the number {number.text} isn't in the input")
    source_text = source if isinstance(source, str) else json.dumps(source, ensure_ascii=False)
    errors += _name_errors(stripped, source_text, meta)
    errors += _timing_errors(stripped, source)
    return errors


def verify_live_square(question: str, options: list[str], correct: str,
                       allowed: list[str]) -> list[str]:
    """A live square: a short question, unique options from the template's set, and exactly
    one of them the answer computed by code (spec 8.7)."""
    errors = []
    if not question.strip():
        errors.append("the question is empty")
    if len(question) > QUESTION_LIMIT:
        errors.append(f"the question is over {QUESTION_LIMIT} characters")
    if BETTING.search(question):
        errors.append("uses betting language")
    if len(options) < 2:
        errors.append("needs at least two options")
    if len(set(options)) != len(options):
        errors.append("options repeat")
    if options.count(correct) != 1:
        errors.append(f"exactly one option must be the correct answer {correct!r}")
    stray = [o for o in options if o not in allowed]
    if stray:
        errors.append(f"options {stray} aren't in the template's set {allowed}")
    return errors
