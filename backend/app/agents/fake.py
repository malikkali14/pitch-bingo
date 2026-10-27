"""A chat client that never leaves the process, for tests and offline runs (spec 12.1).

Give it canned replies (strings come back as the assistant's text, exceptions are raised, and
the last reply repeats once the others are used up), or a function of the call. It records
every call so tests can check prompts.
"""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, Message

Reply = str | BaseException
Script = Sequence[Reply] | Callable[["Call"], Reply]


@dataclass
class Call:
    prompt: str                 # the last user message
    instructions: str
    options: dict[str, Any] = field(default_factory=dict)


class FakeChatClient(BaseChatClient):
    def __init__(self, replies: Script, delay: float = 0.0) -> None:
        super().__init__()
        self.script = replies if callable(replies) else list(replies)
        self.delay = delay
        self.calls: list[Call] = []

    def _inner_get_response(self, *, messages: Sequence[Message], stream: bool,
                            options: Mapping[str, Any], **kwargs: Any) -> Any:
        return self._respond(messages, options)

    async def _respond(self, messages: Sequence[Message], options: Mapping[str, Any]
                       ) -> ChatResponse:
        user = [m for m in messages if m.role == "user"]
        call = Call(user[-1].text if user else "", str(options.get("instructions") or ""),
                    dict(options))
        self.calls.append(call)
        if self.delay:
            await asyncio.sleep(self.delay)
        if callable(self.script):
            reply = self.script(call)
        elif self.script:
            reply = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        else:
            raise RuntimeError("FakeChatClient has no reply left")
        if isinstance(reply, BaseException):
            raise reply
        return ChatResponse(messages=[Message("assistant", [reply])])
