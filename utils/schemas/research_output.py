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
    """One issue investigated within a broader topic."""

    issue: str
    summary: str
    supporting_urls: list[str] = Field(default_factory=list)


class LeadResearcherOutput(BaseModel):
    """Final validated synthesis returned by the lead researcher."""

    final_summary: str
    findings: list[TopicFinding] = Field(default_factory=list)
    legislation_sources: list[str] = Field(default_factory=list)
