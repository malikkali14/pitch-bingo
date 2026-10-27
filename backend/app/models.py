"""Pydantic messages (spec 9.4): sessions, the replay stream and the game."""

import time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


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


class AnswerSubmit(BaseModel):
    type: Literal["answer.submit"]
    square_id: str
    value: str | int


class BoardMove(BaseModel):
    """Cells are {"row": r, "col": c} (or [r, c]); the game validates them."""

    type: Literal["board.move"]
    from_cell: Any
    to_cell: Any


class StrategyApply(BaseModel):
    type: Literal["strategy.apply"]
    advice_id: str


class ProfileSet(BaseModel):
    """Profile fields. The card is built before kickoff, so mid-match only the strategist
    setting, handle and language change; mode, club and focus player stay as built."""

    model_config = ConfigDict(extra="ignore")
    type: Literal["profile.set"]
    strategist: Literal["auto", "suggest", "manual"] | None = None
    handle: str | None = Field(default=None, max_length=24)
    language: str | None = None


Client = ReplaySpeed | DevPause | DevJump | AnswerSubmit | BoardMove | StrategyApply | ProfileSet
ClientMessage = Annotated[Client, Field(discriminator="type")]
client_message: TypeAdapter[Client] = TypeAdapter(ClientMessage)


def wall_ms() -> int:
    return int(time.time() * 1000)


def message(type_: str, t: float, **payload: Any) -> dict[str, Any]:
    """A server message: type, t (match seconds) and wall (server time in ms), then the payload."""
    return {"type": type_, "t": round(t, 2), "wall": wall_ms(), **payload}
