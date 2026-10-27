"""Foundry chat clients (spec 8.2, 10.1, 10.2).

One client per model deployment, shared by every session: gpt-4.1-mini (FOUNDRY_MODEL_FAST) for
the real-time agents, gpt-5-mini (FOUNDRY_MODEL_QUALITY) for the recap and the rules tutor.
DefaultAzureCredential means managed identity in Azure and `az login` locally, so no keys.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from app.config import Settings, settings

Tier = Literal["fast", "quality"]


@dataclass(frozen=True)
class ChatClients:
    # SupportsChatGetResponse: a FoundryChatClient, or a FakeChatClient in tests.
    fast: Any
    quality: Any
    fast_model: str
    quality_model: str

    def for_tier(self, tier: Tier) -> Any:
        return self.fast if tier == "fast" else self.quality


def build_clients(config: Settings = settings) -> ChatClients | None:
    """None when no Foundry endpoint is configured: every agent then uses its fallback."""
    if not config.foundry_project_endpoint:
        return None
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    credential = DefaultAzureCredential()

    def client(model: str) -> Any:
        return FoundryChatClient(project_endpoint=config.foundry_project_endpoint, model=model,
                                 credential=credential)

    return ChatClients(client(config.foundry_model_fast), client(config.foundry_model_quality),
                       config.foundry_model_fast, config.foundry_model_quality)


@lru_cache(maxsize=1)
def shared_clients() -> ChatClients | None:
    """The process-wide clients, built on first use."""
    return build_clients(settings)
