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
    """Jump to match second t, or to a display-clock minute (45 and over is the second half)."""

    type: Literal["dev.jump"]
    t: float | None = Field(default=None, ge=0)
    minute: float | None = Field(default=None, ge=0, le=130)


class DevNarratorDown(BaseModel):
    """The failure switch: force the narrator's circuit breaker open (spec 3, 8.8)."""

    type: Literal["dev.narrator_down"]
    on: bool


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


class RecapRequest(BaseModel):
    """A catch-up recap on demand (spec 3, 9.4)."""

    type: Literal["recap.request"]
    kind: Literal["catch_up"] = "catch_up"


class DefinitionRequest(BaseModel):
    """Tap a stat or cue for a one-line explanation (spec 5.1). Not in 9.4's list: added."""

    type: Literal["definition.request"]
    term: str = Field(max_length=40)


class ProfileSet(BaseModel):
    """Profile fields. The card is built before kickoff, so mid-match only the strategist
    setting, handle and language change; mode, club and focus player stay as built."""

    model_config = ConfigDict(extra="ignore")
    type: Literal["profile.set"]
    strategist: Literal["auto", "suggest", "manual"] | None = None
    handle: str | None = Field(default=None, max_length=24)
    language: str | None = None


Client = (ReplaySpeed | DevPause | DevJump | DevNarratorDown | AnswerSubmit | BoardMove
          | StrategyApply | ProfileSet | RecapRequest | DefinitionRequest)
ClientMessage = Annotated[Client, Field(discriminator="type")]
client_message: TypeAdapter[Client] = TypeAdapter(ClientMessage)


def wall_ms() -> int:
    return int(time.time() * 1000)


def message(type_: str, t: float, **payload: Any) -> dict[str, Any]:
    """A server message: type, t (match seconds) and wall (server time in ms), then the payload."""
    return {"type": type_, "t": round(t, 2), "wall": wall_ms(), **payload}
