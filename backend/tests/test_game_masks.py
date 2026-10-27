"""Masks and hold-backs (spec 4.9)."""

from factories import AWAY, HOME
from game_helpers import kickoff, new_game, of, square
from test_game_windows import deadline_square


def foul(log, t, team=AWAY, player="KVL-04"):
    return log.add("foul", t, team=team, player=player, tags=("fouls",), fouled_id="NBA-08",
                   severity=0.2, advantage=False)


def test_first_to_happen_masks_run_from_kickoff():
    game, clock, log = new_game()
    initial = game.initial_messages()
    firsts = [s for s in game.board.squares if s.kind == "first" and s.masks]
    assert sorted(m["square_id"] for m in of(initial, "mask.on")) == sorted(s.id for s in firsts)
    assert {"fouls", "corners", "shots", "offsides", "cards", "subs", "goals"} <= \
        game.masks.tags()


def test_first_mask_lifts_when_its_window_closes():
    game, clock, log = new_game()
    kickoff(game, log)
    first_foul = square(game, "first_foul")
    game.on_event(foul(log, 60.0))
    clock.advance(20)
    out = game.on_tick(70.0)
    assert {"type": "mask.off", "square_id": first_foul.id, "tags": ["fouls"]} in out
    # First free kick also masks fouls until a free kick happens.
    assert "fouls" in game.masks.tags()


def test_deadline_masks_only_during_the_window():
    game, clock, log = new_game()
    kickoff(game, log)
    sq = deadline_square(game, 900, "possession")
    assert "possession" not in game.masks.tags()
    game.on_tick(900.0)
    assert "possession" in game.masks.tags()
    clock.advance(20)
    game.on_tick(905.0)
    assert "possession" not in game.masks.tags()
    assert sq.state == "missed"


def test_events_with_masked_tags_are_held_then_revealed():
    game, clock, log = new_game()
    kickoff(game, log)
    first_foul = square(game, "first_foul")
    event = foul(log, 60.0)
    game.on_event(event)
    assert game.hold(event)                                  # posted during the window
    clock.advance(20)
    out = game.on_tick(70.0)
    reveal = of(out, "feed.reveal")
    # Still masked by "Who wins the first free kick?", so it stays held.
    assert not reveal and first_foul.state == "missed"
    free_kick = log.add("free_kick", 75.0, team=HOME, player="NBA-08", tags=("restarts",))
    game.on_event(free_kick)
    clock.advance(20)
    out = game.on_tick(80.0)
    assert of(out, "feed.reveal") == [{"type": "feed.reveal", "entry_ids": [event["event_id"]]}]


def test_events_without_masked_tags_post_at_once():
    game, clock, log = new_game()
    kickoff(game, log)
    log.pass_(30.0)
    assert not game.hold(log.events[-1])


def test_live_square_holds_its_call():
    game, clock, log = new_game("normal")
    kickoff(game, log)
    log.pass_(598.0, HOME, "NBA-08", outcome="offside", pass_type="through_ball")
    game.on_event(log.events[-1])
    offside = log.add("offside", 600.0, team=HOME, player="NBA-09", tags=("offsides",))
    out = game.on_event(offside, significance=60)
    added = of(out, "square.added")[0]["square"]
    assert of(out, "mask.on")[0]["square_id"] == added["id"]
    assert game.hold(offside)


def test_too_early_square_keeps_its_mask_until_the_event_window_ends():
    game, clock, log = new_game()
    kickoff(game, log)
    first_corner = square(game, "first_corner")
    game.answer(first_corner.id, HOME)
    assert first_corner.state == "too_early" and "corners" in game.masks.tags()
    game.on_event(log.add("corner", 300.0, team=HOME, player="NBA-07", tags=("corners",)))
    clock.advance(19)
    game.on_tick(310.0)
    assert "corners" in game.masks.tags()
    clock.advance(1)
    out = game.on_tick(311.0)
    assert {"type": "mask.off", "square_id": first_corner.id, "tags": ["corners"]} in out


def test_stats_are_redacted_while_masked():
    game, clock, log = new_game()
    kickoff(game, log)
    snapshot = {
        "score": {HOME: 1, AWAY: 0},
        "clubs": {team: {"possession": 50.0, "shots": 3, "shots_on_target": 1, "xg": 0.4,
                         "fouls": 2, "corners": 1, "yellow_cards": 0, "red_cards": 0,
                         "offsides": 0, "passes": 10} for team in (HOME, AWAY)},
        "players": {"NBA-08": {"shots": 1, "xg": 0.2, "passes": 4}},
        "patterns": {"pressure": {HOME: {"field_tilt": 55.0}, AWAY: {"field_tilt": 45.0}}},
    }
    redacted = game.redact_stats(snapshot)
    home = redacted["clubs"][HOME]
    assert home["shots"] is None and home["xg"] is None and home["fouls"] is None
    assert home["yellow_cards"] is None and home["corners"] is None
    assert home["passes"] == 10 and home["possession"] == 50.0     # possession not masked yet
    assert redacted["players"]["NBA-08"]["shots"] is None
    assert redacted["players"]["NBA-08"]["passes"] == 4
    assert redacted["score"] == {HOME: 1, AWAY: 0}                  # the score stays visible
    assert "shots" in redacted["masked"]
    assert snapshot["clubs"][HOME]["shots"] == 3                    # the original is untouched
    deadline_square(game, 900, "possession")
    game.on_tick(900.0)
    redacted = game.redact_stats(snapshot)
    assert redacted["clubs"][HOME]["possession"] is None
    assert redacted["patterns"]["pressure"][HOME]["field_tilt"] is None
