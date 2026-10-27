"""Card builder rules (spec 4.1, 4.2, 4.3, 4.10)."""

import pytest

from app.engine.source import MATCHES_DIR, available_seeds, load_match
from app.game.bank import DEFAULT_DEADLINES, FIRST, TEMPLATES
from app.game.card import BLANK_CELLS, LINES, Profile, build_card, validate_deadlines
from app.game.ranges import in_range

META = load_match(MATCHES_DIR / "2610").meta
HOME, AWAY = META["home_team_id"], META["away_team_id"]
FOCUS = next(p["id"] for p in META["teams"][1]["players"] if p["position"] == "ST")


def card(mode: str = "normal", **profile: str | None):
    return build_card(META, Profile.parse({"mode": mode, **profile}, META))


def statics(board):
    return [s for s in board.squares if s.kind != "live"]


def test_twelve_lines_of_five():
    assert len(LINES) == 12
    assert all(len(cells) == 5 for cells in LINES.values())
    assert sorted(LINES) == sorted([f"row:{i}" for i in range(5)] + [f"col:{i}" for i in range(5)]
                                   + ["diag:0", "diag:1"])


@pytest.mark.parametrize("mode", ["normal", "advanced"])
def test_composition(mode):
    board = card(mode)
    assert len(board.squares) == 25
    assert len({s.cell for s in board.squares}) == 25
    kinds = [s.kind for s in statics(board)]
    assert kinds.count("deadline") == 10 and kinds.count("first") == 10
    blanks = [s for s in board.squares if s.kind == "live"]
    assert {s.cell for s in blanks} == set(BLANK_CELLS) == {(0, 0), (0, 4), (2, 2), (4, 0), (4, 4)}
    assert all(s.state == "empty_blank" for s in blanks)
    assert all(s.state == "waiting" for s in statics(board))


def test_default_deadlines():
    assert sorted(s.deadline_s for s in card().squares if s.kind == "deadline") == \
        list(DEFAULT_DEADLINES)


@pytest.mark.parametrize("deadlines,ok", [
    (DEFAULT_DEADLINES, True),
    ((900, 1200, 1800, 2400, 2700, 3300, 3600, 4200, 4800, 5400, 5100), True),       # 11
    ((600, 900, 1200, 1800, 2400, 2700, 3300, 3600, 4200, 4800, 5400, 5100), True),  # 12
    ((900, 1200, 1800, 2400, 2700, 3300, 3600, 4200, 4800), False),                  # 9: too few
    ((540, 1200, 1800, 2400, 2700, 3300, 3600, 4200, 4800, 5400), False),            # before 10'
    ((900, 1200, 1800, 3300, 3600, 4200, 4500, 4800, 5100, 5400), False),            # 3 in 1st half
    ((900, 1200, 1800, 2400, 2700, 3600, 3600, 3600, 4800, 5400), False),            # 3 share 60'
    ((900, 1200, 1800, 2400, 2700, 3600, 3600, 4200, 4800, 5400), True),             # 2 share 60'
])
def test_deadline_rules(deadlines, ok):
    if ok:
        validate_deadlines(deadlines)
        board = build_card(META, Profile.parse({}, META), deadlines=deadlines)
        kinds = [s.kind for s in statics(board)]
        assert kinds.count("deadline") == len(deadlines)
        assert kinds.count("first") == 20 - len(deadlines)
        assert len(board.squares) == 25
    else:
        with pytest.raises(ValueError):
            validate_deadlines(deadlines)


def test_first_squares_use_every_first_template():
    firsts = [s for s in card().squares if s.kind == "first"]
    assert sorted(s.template for s in firsts) == sorted(t.id for t in FIRST)
    assert all(s.trigger and s.deadline_s is None for s in firsts)


@pytest.mark.parametrize("seed", available_seeds())
@pytest.mark.parametrize("mode", ["normal", "advanced"])
def test_text_at_most_60_characters(seed, mode):
    meta = load_match(MATCHES_DIR / str(seed)).meta
    for team in meta["teams"]:
        for player in team["players"]:
            board = build_card(meta, Profile.parse(
                {"mode": mode, "club": team["id"], "focus_player_id": player["id"]}, meta))
            for s in statics(board):
                assert 0 < len(s.text["en"]) <= 60, s.text


@pytest.mark.parametrize("mode,expected", [
    ("normal", {"team", "number", "yesno"}),
    ("advanced", {"team", "number", "yesno", "player"}),
])
def test_answer_types_by_mode(mode, expected):
    board = card(mode, club=HOME, focus_player_id=FOCUS)
    assert {s.answer_type for s in statics(board)} == expected
    for s in statics(board):
        template = TEMPLATES[s.template]
        assert s.answer_type == (template.normal if mode == "normal" else template.advanced)
        assert list(s.masks) == list(template.masks)
        assert s.resolver == template.resolver


def test_normal_numbers_are_three_ranges_covering_every_count():
    for s in card("normal").squares:
        if s.answer_type != "number":
            continue
        assert len(s.options) == 3 and s.option_labels["en"]
        for count in range(40):
            assert sum(in_range(key, count) for key in s.options) == 1, (s.options, count)


def test_advanced_numbers_are_exact():
    assert all(s.options == [] for s in card("advanced").squares if s.answer_type == "number")


def test_team_options():
    board = card()
    for s in statics(board):
        if s.answer_type == "team":
            expected = [HOME, AWAY, "level"] if TEMPLATES[s.template].level else [HOME, AWAY]
            assert s.options == expected
        if s.answer_type == "yesno":
            assert s.options == ["yes", "no"]


def test_end_of_half_deadlines_say_which():
    texts = {s.deadline_s: s.text["en"] for s in card().squares if s.kind == "deadline"}
    assert "45:00" in texts[2700] and "90:00" in texts[5400]
    assert "15'" in texts[900]


def test_minimum_deadline_per_template():
    for mode in ("normal", "advanced"):
        for s in card(mode).squares:
            if s.kind == "deadline":
                assert s.deadline_s >= TEMPLATES[s.template].min_deadline_s


@pytest.mark.parametrize("profile", [
    {"club": HOME}, {"club": AWAY}, {"focus_player_id": FOCUS},
    {"club": HOME, "focus_player_id": FOCUS},
])
def test_at_least_16_statics_shared_with_neutral(profile):
    def key(s):
        return (s.id, s.text["en"], s.cell, tuple(s.options))
    neutral = {key(s) for s in statics(card())}
    tailored = card(**profile)
    shared = [s for s in statics(tailored) if key(s) in neutral]
    assert len(shared) >= 16
    assert {s.cell for s in tailored.squares} == {s.cell for s in card().squares}


def test_tailored_squares():
    board = card(club=AWAY, focus_player_id=FOCUS)
    club_name = next(t["short_name"] for t in META["teams"] if t["id"] == AWAY)
    surname = next(p["surname"] for t in META["teams"] for p in t["players"] if p["id"] == FOCUS)
    club = [s for s in board.squares if s.template == "club_fouls"]
    focus = [s for s in board.squares if s.template == "focus_shot"]
    assert len(club) == 2 and all(club_name in s.text["en"] for s in club)
    assert len(focus) == 2 and all(surname in s.text["en"] for s in focus)
    assert not [s for s in card().squares if s.template in ("club_fouls", "focus_shot")]


def test_same_inputs_same_card():
    a, b = card("advanced", club=HOME), card("advanced", club=HOME)
    assert [s.view() for s in a.squares] == [s.view() for s in b.squares]


def test_modes_differ_in_layout_or_wording():
    normal, advanced = card("normal"), card("advanced")
    assert [s.answer_type for s in normal.squares] != [s.answer_type for s in advanced.squares]


def test_profile_rejects_unknown_ids():
    with pytest.raises(ValueError):
        Profile.parse({"club": "XXX"}, META)
    with pytest.raises(ValueError):
        Profile.parse({"focus_player_id": "nobody"}, META)
    with pytest.raises(ValueError):
        Profile.parse({"mode": "expert"}, META)
    profile = Profile.parse({}, META)
    assert (profile.mode, profile.club, profile.language) == ("normal", None, "en")
    assert profile.strategist == "auto"
    assert Profile.parse({"mode": "advanced"}, META).strategist == "suggest"
    assert Profile.parse({"club": "neutral"}, META).club is None


def test_view_matches_frontend_square_shape():
    view = card().squares[1].view()
    assert set(view) >= {"id", "kind", "text", "answer_type", "options", "deadline_s", "trigger",
                         "resolver", "masks", "cell", "state", "answer", "result",
                         "source_event_ids", "closes_at"}
    assert set(view["cell"]) == {"row", "col"}
    board = card().view()
    assert set(board) >= {"squares", "scored_lines", "points", "correct", "bingos"}
