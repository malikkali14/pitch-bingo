"""Settings read from the environment (spec 11.5).

Agent Framework does not load .env files by itself, so load_dotenv() runs here.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    foundry_project_endpoint: str = ""
    foundry_model_fast: str = "gpt-4.1-mini"
    foundry_model_quality: str = "gpt-5-mini"
    storage: str = "memory"
    cosmos_endpoint: str = ""
    cosmos_database: str = "pitchbingo"
    applicationinsights_connection_string: str = ""
    enable_instrumentation: bool = False
    enable_sensitive_data: bool = False
    otel_service_name: str = "pitch-bingo"
    default_seed: int = 2610
    languages: list[str] = field(default_factory=lambda: ["en", "fr"])
    dev_panel: bool = True


def load_settings() -> Settings:
    return Settings(
        foundry_project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT", ""),
        foundry_model_fast=os.getenv("FOUNDRY_MODEL_FAST", "gpt-4.1-mini"),
        foundry_model_quality=os.getenv("FOUNDRY_MODEL_QUALITY", "gpt-5-mini"),
        storage=os.getenv("STORAGE", "memory"),
        cosmos_endpoint=os.getenv("COSMOS_ENDPOINT", ""),
        cosmos_database=os.getenv("COSMOS_DATABASE", "pitchbingo"),
        applicationinsights_connection_string=os.getenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING", ""
        ),
        enable_instrumentation=_flag("ENABLE_INSTRUMENTATION", False),
        enable_sensitive_data=_flag("ENABLE_SENSITIVE_DATA", False),
        otel_service_name=os.getenv("OTEL_SERVICE_NAME", "pitch-bingo"),
        default_seed=int(os.getenv("DEFAULT_SEED", "2610")),
        languages=[s.strip() for s in os.getenv("LANGUAGES", "en,fr").split(",") if s.strip()],
        dev_panel=_flag("DEV_PANEL", True),
    )


settings = load_settings()
