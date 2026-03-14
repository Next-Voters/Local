"""Shared Pydantic models used across agents and tools."""

from pydantic import BaseModel, Field


class ReflectionEntry(BaseModel):
    """Structured reflection produced by the reflection tool."""

    reflection: str = Field(
        description="Based on the current conversation that you have had, build a complete, but succinct reflection to create enriched context for agent"
    )
    gaps_identified: list[str] = Field(
        default_factory=list,
        description="Information gaps or missing context that needs to be addressed",
    )
    next_action: str = Field(
        description="Specific action planned for the next iteration (e.g., search query, tool to use)"
    )


class IndividualReliabilityAnalysis(BaseModel):
    """Reliability judgment for a single source."""

    score: str = Field(
        description="Assign a score on how reliable the source is. Look for .edu .gov and city sources like brampton.ca when giving a score. Create a bias towards government ran websites to ensure non-partisian involvement."
    )
    rationale: str = Field(
        description="Explain your choice for the scoring in 250 characters or less"
    )

class WriterOutput(BaseModel):
    """Structured reflection output produced by the reflection tool."""

    title: str = Field(
        description="Title of the written content"
    )
    body: str = Field(
        description="Main written content"
    )
    summary: str = Field(
        description="Brief summary of the content"
    )
