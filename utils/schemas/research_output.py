"""Structured output models enforced via create_agent's response_format.

These Pydantic models define the contract between agents. The model MUST
produce valid structured output matching these schemas — validation errors
fail fast rather than silently corrupting downstream data.
"""

from pydantic import BaseModel, Field


class ResearcherOutput(BaseModel):
    """Final output returned by a researcher subagent."""

    research_summary: str = Field(
        description="Concise summary of findings for the researched issue."
    )
    legislation_sources: list[str] = Field(
        default_factory=list,
        description="Source URLs supporting the findings.",
    )


class TopicFinding(BaseModel):
    """One legislation section structured for email rendering."""

    headline: str = Field(
        description="Short, punchy section title suitable for an email header. "
        "Written like a news alert — specific and human, not a government memo."
    )
    priority: int = Field(
        default=1,
        description="Rendering priority (1 = highest impact). Determines section order.",
    )
    summary: list[str] = Field(
        default_factory=list,
        description="Short bullet points (one sentence each) stating a single fact or action. "
        "Max 4 bullets. No paragraphs.",
    )
    expanded_content: str = Field(
        default="",
        description="1-2 sentence expanded context for readers who want more detail. "
        "Kept short for mobile readability.",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Source URLs backing this finding.",
    )


class LeadResearcherOutput(BaseModel):
    """Structured publication state — render-ready for the HTML email report."""

    overview: str = Field(
        description="One-sentence topic overview suitable for a TOC entry or email subject.",
    )
    findings: list[TopicFinding] = Field(
        default_factory=list,
        description="Legislation sections ordered by priority (1 = highest). "
        "Each finding is a self-contained report section.",
    )
    legislation_sources: list[str] = Field(
        default_factory=list,
        description="Flat deduplicated list of all source URLs across findings.",
    )
