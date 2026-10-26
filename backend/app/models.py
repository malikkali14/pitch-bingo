"""Pydantic messages (spec 9.4). This phase covers sessions and the replay stream."""

import time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class CreateSession(BaseModel):
    seed: int | None = None
    profile: dict[str, Any] = Field(default_factory=dict)


class SessionCreated(BaseModel):
    session_id: str


class ReplaySpeed(BaseModel):
    type: Literal["replay.speed"]
    speed: Literal[1, 5, 10]


class DevPause(BaseModel):
    type: Literal["dev.pause"]
    on: bool


class DevJump(BaseModel):
    type: Literal["dev.jump"]
    t: float = Field(ge=0)


ClientMessage = Annotated[ReplaySpeed | DevPause | DevJump, Field(discriminator="type")]
client_message: TypeAdapter[ReplaySpeed | DevPause | DevJump] = TypeAdapter(ClientMessage)


def wall_ms() -> int:
    return int(time.time() * 1000)


def message(type_: str, t: float, **payload: Any) -> dict[str, Any]:
    """A server message: type, t (match seconds) and wall (server time in ms), then the payload."""
    return {"type": type_, "t": round(t, 2), "wall": wall_ms(), **payload}
