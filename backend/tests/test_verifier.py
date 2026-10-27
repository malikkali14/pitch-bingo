"""The verifier (spec 8.7): every number and name in AI text is checked against the input."""

import pytest
from factories import load_meta

from app.verify.verifier import numbers_in, verify_line, verify_live_square

META = load_meta()
INPUT = {
    "event": {"type": "shot", "clock": "33:23", "player": "Arvel", "team": "Northbridge",
              "ball_speed_kmh": 92.3, "xg": 0.153},
    "stats": {"possession": {"Northbridge": 61.5, "Kestrel Vale": 38.5}, "shots": 5,
              "distance_m": 24.6},
    "score": "1-0",
}


def surname(i: int = 0, team: int = 0) -> str:
    return str(META["teams"][team]["players"][i]["surname"])


@pytest.fixture
def named_input() -> dict:
    return {**INPUT, "event": {**INPUT["event"], "player": surname(8)}}


@pytest.mark.parametrize("text", [
    "A shot at 92 km/h, worth 0.15 xG.",            # speed to 0.5 km/h, xG to 0.01
    "Un tir à 92 km/h, 0,15 xG.",                     # the French decimal comma
    "Northbridge have 62% of the ball.",              # percentages to 1 point
    "Their 5th shot, from 25 m, at 33'.",             # counts and minutes exactly, metres to 0.5
    "Still 1-0.",
])
def test_numbers_from_the_input_pass(text):
    assert verify_line(text, INPUT, META, "advanced") == []


@pytest.mark.parametrize("text,bad", [
    ("A shot at 97 km/h.", "97"),                     # invented speed
    ("Worth 0.21 xG.", "0.21"),
    ("Worth 0,21 xG.", "0,21"),
    ("Their 6th shot.", "6"),                          # counts are exact
    ("Northbridge have 64% of the ball.", "64"),
])
def test_invented_numbers_fail(text, bad):
    errors = verify_line(text, INPUT, META, "advanced")
    assert any(bad in e for e in errors), errors


def test_number_reading():
    assert [n.value for n in numbers_in("0,15 and 0.15, 45+2, 3rd, 61%")] == \
        [0.15, 0.15, 45, 2, 3, 61]
    assert numbers_in("61%")[0].percent


def test_names_must_be_in_the_match_and_the_input(named_input):
    player = surname(8)
    assert verify_line(f"{player} lets fly for Northbridge.", named_input, META, "normal") == []
    other = surname(9)                                # a real player, but not in this moment
    assert any(other in e for e in verify_line(f"{other} shoots.", named_input, META, "normal"))


def test_unknown_names_fail(named_input):
    errors = verify_line("Then Zlatanovic scores for Northbridge.", named_input, META, "normal")
    assert any("Zlatanovic" in e for e in errors)


@pytest.mark.parametrize("word", ["odds", "bet", "wager", "stake", "Betting"])
def test_betting_words_fail(word):
    assert any("betting" in e for e in verify_line(f"The {word} shift.", INPUT, META, "normal"))


def test_ordinary_words_that_contain_betting_words_pass():
    assert verify_line("A mistake, but better now.", INPUT, META, "normal") == []


@pytest.mark.parametrize("mode,limit", [("normal", 140), ("advanced", 220)])
def test_length_limits(mode, limit):
    assert verify_line("a" * limit, INPUT, META, mode) == []
    assert any("long" in e for e in verify_line("a" * (limit + 1), INPUT, META, mode))


def test_empty_text_fails():
    assert verify_line("  ", INPUT, META, "normal")


@pytest.mark.parametrize("options,correct,ok", [
    (["foul", "offside", "advantage"], "offside", True),
    (["foul", "foul", "offside"], "offside", False),          # duplicate options
    (["foul", "advantage"], "offside", False),                 # no correct option
    (["offside", "offside"], "offside", False),               # two correct options
    (["foul", "corner"], "foul", False),                        # not from the template's set
    (["foul"], "foul", False),                                  # too few
])
def test_live_square_options(options, correct, ok):
    errors = verify_live_square("What did the referee just give?", options, correct,
                                ["foul", "offside", "advantage", "no_call"])
    assert (errors == []) == ok, errors


def test_live_square_question_length():
    errors = verify_live_square("x" * 61, ["foul", "offside"], "foul", ["foul", "offside"])
    assert any("60" in e for e in errors)
