"""Live squares (spec 4.11)."""

import json

import pytest
from factories import AWAY, HOME
from game_helpers import FakeTime, kickoff, new_game, of

from app.engine.source import MATCHES_DIR, available_seeds, load_match
from app.game.card import Profile
from app.game.game import Game
from app.game.live import SEGMENTS, clock_seconds, restart_after
from app.stats.engine import StatsEngine

SHIPPED = available_seeds()


def planted(seed):
    summary = json.loads((MATCHES_DIR / str(seed) / "summary.json").read_text())
    return {p["segment"] for p in summary["planted"]}


def play(meta, events, mode="normal", plants=frozenset(), **profile):
    """Run a whole match through a game, with significance from the stats engine."""
    clock = FakeTime()
    game = Game(meta, Profile.parse({"mode": mode, **profile}, meta), now=clock.now,
                wall_ms=clock.wall_ms, planted=plants)
    stats = StatsEngine(meta)
    added = []
    for e in events:
        score = stats.on_event(e).significance
        for m in game.on_event(e, significance=score):
            if m["type"] == "square.added":
                added.append((e, m["square"]))
    return game, added


def offside_moment(game, log):
    log.pass_(598.0, HOME, "NBA-08", outcome="offside", length_m=25.0, pass_type="through_ball")
    game.on_event(log.events[-1])
    return game.on_event(log.add("offside", 600.0, team=HOME, player="NBA-09",
                                 tags=("offsides",)), significance=60)


def lives(game):
    return [s for s in game.board.squares if s.kind == "live" and s.state != "empty_blank"]


@pytest.mark.parametrize("seed", SHIPPED)
@pytest.mark.parametrize("mode", ["normal", "advanced"])
def test_exactly_five_one_per_segment(seed, mode):
    data = load_match(MATCHES_DIR / str(seed))
    game, added = play(data.meta, data.events, mode, planted(seed))
    assert len(added) == 5 and len(lives(game)) == 5
    segments = [game.live.segment_of[sq["id"]] for _, sq in added]
    assert segments == [0, 1, 2, 3, 4]
    for (event, _), seg in zip(added, segments, strict=True):
        start, end = SEGMENTS[seg]
        assert clock_seconds(event["clock"]) >= start


def test_demo_match_uses_the_planted_moments():
    data = load_match(MATCHES_DIR / "2610")
    normal, added = play(data.meta, data.events, "normal", planted(2610))
    advanced, added_adv = play(data.meta, data.events, "advanced", planted(2610))
    for (event, _), (event_adv, _) in zip(added, added_adv, strict=True):
        assert event is event_adv                     # same moments for every viewer
        assert "planted" in event["tags"]
    by_order = lambda game, added: [game.board.get(sq["id"]) for _, sq in added]  # noqa: E731
    n = by_order(normal, added)
    a = by_order(advanced, added_adv)
    assert [(s.template, s.correct_answer) for s in n] == [
        ("referee", "advantage"), ("referee", "offside"), ("restart", "corner"),
        ("restart", "corner"), ("restart", "goal_kick")]
    assert [s.template for s in a] == [
        "shot_xg", "pass_length", "shot_speed", "move_passes", "pass_length"]
    assert a[3].correct_answer == "13+"
    assert a[4].correct_answer in ("35-50", "50+")   # the 45 m switch


@pytest.mark.parametrize("seed", range(1, 21))
def test_five_per_match_without_planted_moments(seed):
    from app.generator import generate
    match = generate(seed, with_tracking=False)
    game, added = play(match["match"], match["events"], "advanced")
    assert [game.live.segment_of[sq["id"]] for _, sq in added] == [0, 1, 2, 3, 4]


def test_quiet_segment_falls_back_at_85_percent():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    log.pass_(1000.0, HOME, "NBA-08")
    game.on_event(log.events[-1])
    quiet = game.on_event(log.add("foul", 1060.0, team=AWAY, player="KVL-04", tags=("fouls",),
                                  fouled_id="NBA-08", severity=0.1, advantage=False))
    assert not of(quiet, "square.added")             # 17:40 is before 17:45 (85% of 5-20')
    game.on_event(log.add("free_kick", 1065.0, team=HOME, player="NBA-08"))
    log.pass_(1066.0, HOME, "NBA-08")
    game.on_event(log.events[-1])
    out = game.on_event(log.add("foul", 1080.0, team=AWAY, player="KVL-04",
                                tags=("fouls",), fouled_id="NBA-08", severity=0.1,
                                advantage=False))
    added = of(out, "square.added")
    assert len(added) == 1 and game.live.segment_of[added[0]["square"]["id"]] == 0
    sq = game.board.get(added[0]["square"]["id"])
    assert sq.template == "referee" and sq.correct_answer == "foul"


def test_high_scoring_pattern_events_alone_are_not_candidates():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    log.pass_(600.0, HOME, "NBA-08")
    game.on_event(log.events[-1], significance=60)    # a short pass: no template fits it
    out = game.on_event(log.add("foul", 610.0, team=AWAY, player="KVL-04", tags=("fouls",),
                                fouled_id="NBA-08", severity=0.1, advantage=False))
    assert not of(out, "square.added")


def test_candidate_then_call_makes_a_live_square():
    game, clock, log = new_game("advanced")
    kickoff(game, log)
    log.pass_(600.0, HOME, "NBA-08", length_m=42.0)
    game.on_event(log.events[-1], significance=60)    # 42 m pass: pass length fits
    out = game.on_event(log.add("out_of_play", 603.0, team=None, x=60.0, y=68.0,
                                last_touch_team_id=HOME))
    added = of(out, "square.added")
    assert len(added) == 1
    sq = game.board.get(added[0]["square"]["id"])
    assert sq.template == "pass_length" and sq.correct_answer == "35-50"


@pytest.mark.parametrize("seed", SHIPPED)
def test_restart_rule_matches_the_match(seed):
    events = load_match(MATCHES_DIR / str(seed)).events
    home = load_match(MATCHES_DIR / str(seed)).meta["home_team_id"]
    away = load_match(MATCHES_DIR / str(seed)).meta["away_team_id"]
    checked = 0
    for i, e in enumerate(events):
        if e["type"] != "out_of_play":
            continue
        nxt = next((n for n in events[i + 1:] if n["type"] in
                    ("throw_in", "corner", "goal_kick", "kickoff", "period_end")), None)
        if nxt is None or nxt["type"] in ("kickoff", "period_end"):
            continue
        kind, team = restart_after(e, home, away)
        assert (kind, team) == (nxt["type"], nxt["team_id"]), e
        checked += 1
    assert checked > 30


@pytest.mark.parametrize("mode", ["normal", "advanced"])
def test_options_have_exactly_one_correct_answer(mode):
    for seed in SHIPPED:
        data = load_match(MATCHES_DIR / str(seed))
        game, added = play(data.meta, data.events, mode, planted(seed))
        for _, view in added:
            sq = game.board.get(view["id"])
            assert len(set(sq.options)) == len(sq.options) >= 2
            assert sq.options.count(sq.correct_answer) == 1
            assert 0 < len(sq.text["en"]) <= 60
            assert len(sq.option_labels["en"]) == len(sq.options)
            assert sq.source_event_ids
            assert "correct_answer" not in view and view["kind"] == "live"


def test_live_window_is_announced_and_scores_150():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    out = offside_moment(game, log)
    added = of(out, "square.added")
    sq_id = added[0]["square"]["id"]
    assert added[0]["square"]["state"] == "open"
    assert of(out, "square.window_open")[0]["square_id"] == sq_id
    assert of(out, "board.update")
    result = of(game.answer(sq_id, "offside"), "square.result")[0]
    assert result["points"] == 150 and game.board.get(sq_id).state == "wildcard"


def test_wrong_live_answer_stays_wrong():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    out = offside_moment(game, log)
    sq_id = of(out, "square.added")[0]["square"]["id"]
    game.answer(sq_id, "foul")
    assert game.board.get(sq_id).state == "wrong"


def test_live_squares_fill_empty_blanks():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    blanks = {s.id: s.cell for s in game.board.squares if s.state == "empty_blank"}
    out = offside_moment(game, log)
    view = of(out, "square.added")[0]["square"]
    assert view["id"] in blanks
    assert (view["cell"]["row"], view["cell"]["col"]) == blanks[view["id"]]
