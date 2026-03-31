"""Shared Pydantic models used to structure LLM responses."""

from typing import Literal, Optional

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


class IndividualReliabilityAnalysis(BaseModel):
    """Reliability analysis for a source."""

    url: Optional[str] = Field(default=None, description="URL of the source")
    reliability_score: Optional[float] = Field(
        default=None, description="Reliability score 0-1"
    )
    reasoning: Optional[str] = Field(
        default=None, description="Reasoning for the score"
    )


class SourceReliabilityJudgment(BaseModel):
    """Single source reliability judgment."""

    url: str = Field(description="URL of the source")
    organization: str = Field(description="Organization name")
    tier: Literal[
        "highly_reliable", "conditionally_reliable", "unreliable", "unknown"
    ] = Field(description="Reliability classification tier")
    rationale: str = Field(
        description="Reasoning citing specific Wikidata signal, max 200 chars"
    )
    accepted: bool = Field(
        description="True only for highly_reliable or conditionally_reliable"
    )


class ReliabilityAnalysisResult(BaseModel):
    """Structured output from reliability analysis LLM call."""

    judgments: list[SourceReliabilityJudgment] = Field(
        description="One judgment per source"
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
