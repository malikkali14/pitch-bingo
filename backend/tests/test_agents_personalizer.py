"""The personalizer and the per-profile cache (spec 5.7, 8.6)."""

import json
from typing import Any

from factories import load_meta
from test_agents_narrator import STATS, STRIKER, shot_event

from app.agents import personalizer
from app.agents.clients import ChatClients
from app.agents.fake import FakeChatClient
from app.agents.orchestrator import Orchestrator
from app.game.card import Profile

META = load_meta()
INSIGHT = json.dumps({"moment_id": "e000001", "headline_facts": ["A 101 km/h shot is saved."],
                      "why_facts": ["Northbridge have 4 shots to 1."],
                      "tags": [], "evidence_ids": [], "numbers": []})


def line(text: str) -> str:
    return json.dumps({"moment_id": "e000001", "text": text})


def reply(personal: str) -> Any:
    def answer(call: Any) -> str:
        return INSIGHT if "explain football moments" in call.instructions else line(personal)
    return answer


async def narrate(profile: Profile, fake: FakeChatClient) -> list[dict[str, Any]]:
    published: list[dict[str, Any]] = []
    orch = Orchestrator(ChatClients(fake, fake, "f", "f"), META, lambda: profile, published.append)
    orch.on_event(shot_event(), 72, [], [], lambda: STATS, False, shot_xg=0.23)
    await orch.drain()
    return published


def test_profile_hash_uses_only_the_fields_that_change_the_line():
    a = Profile(mode="normal", club="NBA", handle="Sam", strategist="auto")
    b = Profile(mode="normal", club="NBA", handle="Alex", strategist="manual")
    assert personalizer.profile_hash(a) == personalizer.profile_hash(b)
    assert personalizer.profile_hash(a) != personalizer.profile_hash(Profile(mode="advanced",
                                                                            club="NBA"))


async def test_the_personalizer_writes_the_line_for_the_profile():
    fake = FakeChatClient(reply("Your Northbridge are pushing: a 101 km/h shot is saved."))
    published = await narrate(Profile(club="NBA"), fake)
    assert published[0]["text"] == "Your Northbridge are pushing: a 101 km/h shot is saved."
    personal = [c for c in fake.calls if "explain football moments" not in c.instructions][0]
    assert "Northbridge" in personal.prompt and '"mode": "normal"' in personal.prompt


async def test_a_bad_personal_line_falls_back_to_the_rendered_insight():
    fake = FakeChatClient(reply("A 120 km/h rocket!"))
    published = await narrate(Profile(), fake)
    assert published[0]["text"] == "A 101 km/h shot is saved. Northbridge have 4 shots to 1."
    assert published[0]["ai"] is True


async def test_the_same_profile_type_reuses_the_line_without_calls():
    fake = FakeChatClient(reply(f"{STRIKER['surname']} forces a save at 101 km/h."))
    first = await narrate(Profile(club="NBA", handle="Sam"), fake)
    calls = len(fake.calls)
    second = await narrate(Profile(club="NBA", handle="Alex"), fake)
    assert second[0]["text"] == first[0]["text"] and len(fake.calls) == calls
    await narrate(Profile(club="KVL"), fake)
    assert len(fake.calls) > calls
