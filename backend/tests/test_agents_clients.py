"""Foundry client wrapper and the fake client (spec 8.2, 10.2). No test calls Azure."""

import asyncio
import json

import pytest
from agent_framework import Agent
from pydantic import BaseModel

from app.agents.clients import build_clients
from app.agents.fake import FakeChatClient
from app.config import Settings, settings


class Reply(BaseModel):
    text: str


def test_no_endpoint_means_no_clients():
    assert settings.foundry_project_endpoint == ""          # conftest blanks it
    assert build_clients(settings) is None


def test_clients_use_the_fast_and_quality_deployments():
    configured = Settings(foundry_project_endpoint="https://example.invalid/api/projects/p",
                          foundry_model_fast="fast-model", foundry_model_quality="quality-model")
    clients = build_clients(configured)
    assert clients is not None
    assert (clients.fast_model, clients.quality_model) == ("fast-model", "quality-model")
    assert clients.for_tier("fast") is clients.fast
    assert clients.for_tier("quality") is clients.quality


async def test_fake_client_returns_canned_json_as_structured_output():
    fake = FakeChatClient(['{"text": "hello"}'])
    agent = Agent(client=fake, name="probe", instructions="Say hello.")
    response = await agent.run("hi", options={"response_format": Reply})
    assert response.value == Reply(text="hello")
    assert fake.calls[0].prompt == "hi"
    assert fake.calls[0].instructions == "Say hello."


async def test_fake_client_can_fail_or_be_slow():
    fake = FakeChatClient([RuntimeError("boom"), '{"text": "late"}'], delay=0.05)
    agent = Agent(client=fake, name="probe")
    with pytest.raises(Exception, match="boom"):
        await agent.run("one")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(agent.run("two"), 0.01)


async def test_fake_client_can_answer_from_a_function():
    fake = FakeChatClient(lambda call: json.dumps({"text": call.prompt.upper()}))
    response = await Agent(client=fake).run("abc", options={"response_format": Reply})
    assert response.value == Reply(text="ABC")
    assert len(fake.calls) == 1
