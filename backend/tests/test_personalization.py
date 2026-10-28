"""Personalization and language (spec 5, 14.2 phase 7). No test calls Azure."""

import json
from typing import Any

import pytest
from factories import AWAY, HOME, load_meta
from fastapi.testclient import TestClient
from game_helpers import kickoff, new_game, of
from test_agents_narrator import STATS, STRIKER, shot_event
from test_game_moves import _set
from test_game_windows import deadline_square
from test_ws_game import until

from app.agents import personalizer, recap, tutor
from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.agents.orchestrator import Orchestrator
from app.engine.source import MATCHES_DIR, available_seeds, load_match
from app.game import lang
from app.game.card import LINES, Profile, build_card
from app.game.live import LIVE_TEMPLATES, labels_for
from app.game.strategist import Accuracy, suggest
from app.main import app
from app.session import sessions

META = load_meta()


# ---- profile (spec 5.7) --------------------------------------------------------------------

def test_profile_fields():
    p = Profile.parse({"language": "fr", "units": "imperial", "my_metric": "xg"}, META)
    assert (p.language, p.units, p.my_metric) == ("fr", "imperial", "xg")
    d = Profile.parse({}, META)
    assert (d.language, d.units, d.my_metric) == ("en", "metric", None)
    for bad in ({"language": "de"}, {"units": "furlongs"}, {"my_metric": "vibes"}):
        with pytest.raises(ValueError):
            Profile.parse(bad, META)


# ---- the card in both languages (spec 5.4) ---------------------------------------------------

@pytest.mark.parametrize("seed", available_seeds())
@pytest.mark.parametrize("mode", ["normal", "advanced"])
def test_static_squares_are_written_in_every_language(seed, mode):
    meta = load_match(MATCHES_DIR / str(seed)).meta
    for team in meta["teams"]:
        for player in team["players"][:6]:
            board = build_card(meta, Profile.parse(
                {"mode": mode, "club": team["id"], "focus_player_id": player["id"]}, meta))
            for s in board.squares:
                if s.kind == "live":
                    continue
                assert set(s.text) == {"en", "fr"}
                assert 0 < len(s.text["fr"]) <= 60, s.text["fr"]
                if s.options:
                    assert len(s.option_labels["fr"]) == len(s.options)


def test_french_labels():
    board = build_card(META, Profile.parse({"mode": "normal"}, META))
    yesno = next(s for s in board.squares if s.answer_type == "yesno")
    assert yesno.option_labels["fr"] == ["Oui", "Non"]
    level = next(s for s in board.squares if "level" in s.options)
    assert level.option_labels["fr"][-1] == "Égalité"
    assert next(s for s in board.squares if s.template == "first_foul").text["fr"] == \
        "Qui commet la première faute ?"


@pytest.mark.parametrize("template,units,language,expected", [
    ("pass_length", "metric", "en", ["under 20 m", "20–35 m", "35–50 m", "over 50 m"]),
    ("pass_length", "imperial", "en", ["under 22 yd", "22–38 yd", "38–55 yd", "over 55 yd"]),
    ("shot_speed", "imperial", "fr", ["moins de 43 mph", "43–56 mph", "56–68 mph",
                                      "plus de 68 mph"]),
    ("shot_xg", "metric", "fr", ["moins de 0,05", "0,05–0,15", "0,15–0,35", "plus de 0,35"]),
    ("referee", "metric", "fr", ["Faute", "Hors-jeu", "Avantage", "Rien"]),
])
def test_live_labels_follow_language_and_units(template, units, language, expected):
    assert labels_for(LIVE_TEMPLATES[template], language, units) == expected


# ---- French template fallbacks (Foundry off) ----------------------------------------------------

def test_french_explanation_and_void_with_foundry_off():
    game, clock, log = new_game("normal", language="fr")
    kickoff(game, log)
    sq = deadline_square(game, 900, "corners")
    game.on_tick(900.0)
    clock.advance(20)
    explanation = of(game.on_tick(905.0), "square.explanation")[0]["text"]
    assert explanation.startswith("Combien de corners avant 15' ? Réponse : ")
    game.on_event(log.add("period_end", 2880.0, team=None, stoppage_added_s=180))
    game.on_event(log.add("period_start", 2880.0, team=None, period=2, clock="45:00"))
    game.on_event(log.add("period_end", 5800.0, team=None, period=2, stoppage_added_s=300))
    goal = next(s for s in game.board.squares if s.template == "first_goal")
    assert goal.result["explanation"] == "Ce n'est pas arrivé pendant ce match."
    assert sq.state == "missed"


def test_french_strategist_reason():
    game, clock, log = new_game("normal", language="fr")
    for s in game.board.squares:
        _set(s, "live", "empty_blank") if s.kind == "live" else _set(s, s.kind, "wrong")
    for c in LINES["row:1"]:
        sq = game.board.at(c)
        if c == (1, 2):
            sq.state, sq.result = "waiting", None
        else:
            _set(sq, sq.kind, "correct")
    _set(game.board.at((0, 0)), "live", "wildcard")
    advice = suggest(game.board, Accuracy(), 0, language="fr")
    assert advice is not None and advice.reason == \
        "Un joker déplacé dans la ligne 2 pour la compléter."


def test_french_recap_template_with_club_and_player_paragraphs():
    summary = recap.Summary(
        kind="halftime", score={"Northbridge": 1, "Kestrel": 0},
        goals=[{"minute": "15'", "scorer": STRIKER["full_name"], "club": "Northbridge"}],
        stats={"Northbridge": {"possession": 58.2, "shots": 7}, "Kestrel": {"possession": 41.8,
                                                                            "shots": 3}},
        card={"points": 640, "correct": 5, "lines": 0}, club="Northbridge",
        focus={"player": STRIKER["full_name"], "touches": 31, "passes": 20, "shots": 2})
    r = recap.template(summary, "fr")
    assert r.content.headline == "Mi-temps : Northbridge 1–0 Kestrel"
    assert r.content.club_paragraph == "Pour Northbridge : devant au score, 1–0."
    assert r.content.player_paragraph.startswith(f"{STRIKER['full_name']} : 31 ballons touchés")
    assert "58 % du ballon" in " ".join(r.content.paragraphs)
    english = recap.template(summary, "en")
    assert english.content.club_paragraph == "For Northbridge: ahead 1–0."


def test_french_definitions_cover_every_term():
    assert set(tutor.DEFINITIONS_FR) == set(tutor.DEFINITIONS)
    assert "hors-jeu" in tutor.definition("offside", "fr").lower()


def test_french_number_format():
    assert lang.number(0.15, "fr") == "0,15" and lang.number(0.15, "en") == "0.15"


# ---- the same moment, two profiles (14.2 phase 7) ------------------------------------------------

INSIGHT = json.dumps({"moment_id": "e000001", "headline_facts": ["A 101 km/h shot is saved."],
                      "why_facts": [], "tags": [], "evidence_ids": [], "numbers": []})


def by_profile(call: Any) -> str:
    """A fake model that writes for whoever the profile says the viewer is."""
    if "explain football moments" in call.instructions:
        return INSIGHT
    viewer = json.loads(call.prompt.split("INPUT: ", 1)[1])["profile"]
    if viewer["language"] == "fr":
        return json.dumps({"moment_id": "e000001", "text": "Un tir à 101 km/h, arrêté."})
    if viewer.get("units") == "imperial":
        return json.dumps({"moment_id": "e000001", "text": "A 63 mph shot is saved."})
    if viewer.get("favorite_club"):
        return json.dumps({"moment_id": "e000001",
                           "text": f"{viewer['favorite_club']} see a 101 km/h shot saved."})
    return json.dumps({"moment_id": "e000001", "text": "A 101 km/h shot is saved."})


async def render(profile: Profile, script: Any = by_profile) -> list[dict[str, Any]]:
    fake = FakeChatClient(script)
    published: list[dict[str, Any]] = []
    orch = Orchestrator(ChatClients(fake, fake, "f", "f"), META, lambda: profile, published.append)
    orch.on_event(shot_event(), 72, [], [], lambda: STATS, False, shot_xg=0.23)
    await orch.drain()
    return published


async def test_the_same_moment_renders_differently_for_two_profiles():
    neutral = await render(Profile())
    fan = await render(Profile(club=AWAY))
    french = await render(Profile(language="fr"))
    imperial = await render(Profile(units="imperial"))
    texts = [r[0]["text"] for r in (neutral, fan, french, imperial)]
    assert texts == ["A 101 km/h shot is saved.", "Kestrel see a 101 km/h shot saved.",
                     "Un tir à 101 km/h, arrêté.", "A 63 mph shot is saved."]
    assert len(set(texts)) == 4


def test_profile_hash_covers_every_field_that_changes_a_line():
    hashes = {personalizer.profile_hash(p) for p in (
        Profile(), Profile(language="fr"), Profile(units="imperial"), Profile(my_metric="xg"),
        Profile(club=HOME), Profile(focus_player_id=STRIKER["id"]), Profile(mode="advanced"))}
    assert len(hashes) == 7


async def test_imperial_viewers_get_converted_numbers_to_quote():
    fake = FakeChatClient(by_profile)
    orch = Orchestrator(ChatClients(fake, fake, "f", "f"), META,
                        lambda: Profile(units="imperial"), lambda m: None)
    orch.on_event(shot_event(), 72, [], [], lambda: STATS, False)
    await orch.drain()
    personal = [c for c in fake.calls if "explain football moments" not in c.instructions][0]
    assert '"ball_speed_mph": 63' in personal.prompt


async def test_my_metric_reaches_the_personalizer():
    fake = FakeChatClient(by_profile)
    orch = Orchestrator(ChatClients(fake, fake, "f", "f"), META,
                        lambda: Profile(my_metric="possession"), lambda m: None)
    orch.on_event(shot_event(), 72, [], [], lambda: STATS, False)
    await orch.drain()
    personal = [c for c in fake.calls if "explain football moments" not in c.instructions][0]
    assert '"my_metric": "possession"' in personal.prompt


async def test_french_never_falls_back_to_an_english_line():
    def broken(call: Any) -> str:
        return INSIGHT if "explain football moments" in call.instructions else "nonsense"
    assert await render(Profile(language="fr"), broken) == []        # French template stays
    assert (await render(Profile(), broken))[0]["text"] == "A 101 km/h shot is saved."


# ---- focus player (spec 5.3) -------------------------------------------------------------------

async def test_focus_player_gets_a_line_every_ten_match_minutes():
    published: list[dict[str, Any]] = []
    orch = Orchestrator(None, META, lambda: Profile(focus_player_id=STRIKER["id"],
                                                    language="fr"), published.append)
    stats = {"players": {STRIKER["id"]: {"touches": 12, "passes": 8, "shots": 1}}}
    for minute in (0, 3, 9, 10, 15, 21, 24):
        orch.focus_update(minute * 60.0, f"{minute:02d}:00", 1, lambda: stats)
    lines = [m for m in published if m["entry_id"].startswith("focus:")]
    assert [m["clock"] for m in lines] == ["10:00", "21:00"]          # none at kickoff
    assert lines[0]["text"] == (f"{STRIKER['full_name']} jusqu'ici : 12 ballons touchés, "
                                "8 passes, 1 tirs.")
    assert lines[0]["ai"] is False


async def test_focus_player_milestones_are_always_announced():
    published: list[dict[str, Any]] = []
    orch = Orchestrator(None, META, lambda: Profile(focus_player_id=STRIKER["id"]),
                        published.append)
    event = shot_event()
    milestone = {"kind": "passes_50", "t": 600.0, "value": 50, "player_id": STRIKER["id"],
                 "team_id": HOME, "event_id": event["event_id"]}
    orch.on_event(event, 5, [], [milestone], lambda: STATS, False)       # quiet moment
    orch.on_event(event, 5, [], [{**milestone, "player_id": "KVL-04"}], lambda: STATS, False)
    lines = [m for m in published if m["entry_id"].startswith("milestone:")]
    assert len(lines) == 1
    assert lines[0]["text"] == f"Milestone for {STRIKER['full_name']}: 50 passes."


# ---- French end to end, through the API, with the fake client ------------------------------------

FRENCH_LINE = json.dumps({"moment_id": "m", "text": "Un grand moment de ce match."})


def test_french_end_to_end_with_the_fake_client() -> None:
    def reply(call: Any) -> str:
        if "explain football moments" in call.instructions:
            return INSIGHT.replace("A 101 km/h shot is saved.", "A big moment.")
        if "bingo card" in call.instructions:
            assert "in French" in call.prompt
            return json.dumps({"text": "Qu'a décidé l'arbitre ?",
                               "options": ["foul", "offside", "advantage"],
                               "labels": ["Faute", "Hors-jeu", "Avantage"]})
        return FRENCH_LINE
    fake = FakeChatClient(reply)
    sessions.clients = lambda: ChatClients(fake, fake, "fake", "fake")
    try:
        with TestClient(app) as client:
            sid = client.post("/api/sessions", json={"seed": 2610, "profile": {
                "language": "fr"}}).json()["session_id"]
            with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
                ready = until(ws, lambda m: m["type"] == "session.ready")[-1]
                until(ws, lambda m: m["type"] == "leaderboard")
                ws.send_json({"type": "replay.speed", "speed": 10})
                ws.send_json({"type": "dev.jump", "t": 618})
                added = until(ws, lambda m: m["type"] == "square.added", 10)[-1]["square"]
                line = until(ws, lambda m: m["type"] == "feed.replace", 10)[-1]
                ws.send_json({"type": "definition.request", "term": "offside"})
                definition = until(ws, lambda m: m["type"] == "definition")[-1]
    finally:
        sessions.clients = lambda: None
    assert ready["profile"]["language"] == "fr"
    assert all(s["text"].get("fr") for s in ready["card"]["squares"] if s["kind"] != "live")
    assert added["text"]["fr"] == "Qu'a décidé l'arbitre ?"
    assert added["option_labels"]["fr"] == ["Faute", "Hors-jeu", "Avantage"]
    assert added["text"]["en"] == "What did the referee just give?"      # other language kept
    assert line["text"] == "Un grand moment de ce match." and line["ai"] is True
    assert "hors-jeu" in definition["text"].lower()


def test_french_with_foundry_off_end_to_end() -> None:
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"seed": 2610, "profile": {
            "language": "fr"}}).json()["session_id"]
        with client.websocket_connect(f"/ws/sessions/{sid}") as ws:
            until(ws, lambda m: m["type"] == "leaderboard")
            ws.send_json({"type": "replay.speed", "speed": 10})
            ws.send_json({"type": "dev.jump", "t": 2860})
            recap_msg = until(ws, lambda m: m["type"] == "recap", 10)[-1]
            ws.send_json({"type": "definition.request", "term": "possession"})
            definition = until(ws, lambda m: m["type"] == "definition")[-1]
    assert recap_msg["content"]["headline"].startswith("Mi-temps : Northbridge")
    assert definition["ai"] is False and "possession" in definition["text"].lower()
    assert definition["text"] == tutor.definition("possession", "fr")
