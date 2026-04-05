"""Shared Pydantic models used to structure LLM responses."""

from typing import Optional

from pydantic import BaseModel, Field


class ReflectionEntry(BaseModel):
    """Structured reflection produced by the reflection tool."""

    reflection: Optional[str] = Field(
        default=None,
        description="Based on the current conversation that you have had, build a complete, but succinct reflection to create enriched context for agent",
    )
    gaps_identified: list[str] = Field(
        default_factory=list,
        description="Information gaps or missing context that needs to be addressed",
    )
    next_action: Optional[str] = Field(
        default=None,
        description="Specific action planned for the next iteration (e.g., search query, tool to use)",
    )


class WriterOutput(BaseModel):
    """Structured reflection output produced by the reflection tool."""

    title: Optional[str] = Field(
        default=None, description="Title of the written content"
    )
    body: Optional[str] = Field(
        default=None,
        description="Main written content. They should be in bullet-point format.",
    )
    summary: Optional[str] = Field(
        default=None, description="Brief summary of the content"
    )
