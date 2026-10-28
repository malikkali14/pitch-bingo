"""Messages between workflow steps (spec 8.5). LLM agents must return JSON that validates
against these; the verifier then checks the content.

Models an agent returns are sent as a strict structured-output schema, which Azure OpenAI only
accepts when every field is required and there are no free-form objects: so no defaults here
(nullable fields are still required), and numbers are a list of key and value pairs.
"""

from typing import Any

from pydantic import BaseModel, Field


class NumberFact(BaseModel):
    key: str
    value: float


class Insight(BaseModel):
    """The narrator's language-neutral reading of a moment."""

    moment_id: str
    headline_facts: list[str] = Field(description="What happened, one short sentence each.")
    why_facts: list[str] = Field(description="Why it matters right now, one sentence each.")
    tags: list[str]
    evidence_ids: list[str]
    numbers: list[NumberFact] = Field(description="The key numbers used, as key and value.")


class RenderedLine(BaseModel):
    """One feed line for one profile, from the personalizer (or template rendering)."""

    moment_id: str
    text: str


class LiveSquareDraft(BaseModel):
    """The square writer's wording. The correct option is computed by code and never chosen
    here: the writer only words the question and picks which wrong options to show."""

    text: str = Field(description="The question, 60 characters at most.")
    options: list[str] = Field(description="Option keys from the template's set, including the "
                                           "correct one exactly once.")
    labels: list[str] = Field(description="How each option reads, same order as options.")


class Explanation(BaseModel):
    """Evidence ids are known by code (the square's result), so the model isn't asked."""

    square_id: str
    text: str


class Definition(BaseModel):
    """A one-line definition for a tapped stat or cue (spec 5.1)."""

    term: str
    text: str


class StrategyReason(BaseModel):
    reason: str = Field(description="One line, under 120 characters.")


class RecapContent(BaseModel):
    headline: str
    paragraphs: list[str]
    talking_points: list[str]
    club_paragraph: str | None
    player_paragraph: str | None
    bingo_summary: str | None


class Recap(BaseModel):
    kind: str                     # halftime, full_time, catch_up, bingo
    content: RecapContent
    evidence_ids: list[str] = Field(default_factory=list)
    ai: bool = False

    def text_parts(self) -> list[str]:
        c = self.content
        parts: list[Any] = [c.headline, *c.paragraphs, *c.talking_points, c.club_paragraph,
                            c.player_paragraph, c.bingo_summary]
        return [p for p in parts if p]
