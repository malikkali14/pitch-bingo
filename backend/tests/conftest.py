"""Shared test setup. Tests never call Azure (CLAUDE.md, spec 12.1).

The Foundry endpoint is blanked before anything imports the app. load_dotenv() never
overrides a variable that is already set, so a developer's backend/.env can't leak in, and
agent tests inject a FakeChatClient instead.
"""

import os

os.environ["FOUNDRY_PROJECT_ENDPOINT"] = ""
os.environ["ENABLE_INSTRUMENTATION"] = "false"
os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_line_cache():
    """The personalizer's line cache is process-wide; each test starts empty."""
    from app.agents import orchestrator, personalizer
    personalizer.CACHE.clear()
    orchestrator.DEFINITION_CACHE.clear()
