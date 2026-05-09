"""Unit tests for SummaryWriter component.

Tests the SummaryWriter's ability to create accurate,
complete, and well-structured summaries from legislation notes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase

from evals.metrics.summary_quality import (
    SummaryQualityMetric,
    SchemaComplianceMetric,
    create_summary_quality_metric,
)
from evals.metrics.no_hallucination import (
    NoHallucinationMetric,
    ClaimVerifiabilityMetric,
)
from utils.schemas import WriterOutput, LegislationItem


class TestSummaryWriter:
    """Test suite for SummaryWriter component."""

    @pytest.fixture(autouse=True)
    def setup(
        self, sample_legislation_notes: str, sample_writer_output: dict[str, Any]
    ):
        self.notes = sample_legislation_notes
        self.expected_output = sample_writer_output

    def test_writer_output_schema_validation(self):
        """Test WriterOutput schema correctly validates output."""
        valid_output = WriterOutput(
            items=[
                LegislationItem(
                    header="Test headline",
                    bullets=["Test description of legislation."],
                )
            ]
        )

        assert len(valid_output.items) == 1
        assert valid_output.items[0].header == "Test headline"
        assert valid_output.items[0].bullets == ["Test description of legislation."]

    def test_writer_output_optional_fields(self):
        """Test WriterOutput handles empty items list correctly."""
        minimal_output = WriterOutput()

        assert minimal_output.items == []

    @patch("pipelines.node.summary_writer._get_model")
    def test_summary_writer_produces_valid_schema(
        self,
        mock_model: MagicMock,
        sample_legislation_notes: str,
    ):
        """Test that summary writer produces valid WriterOutput."""
        mock_model.return_value.invoke.return_value = WriterOutput(
            items=[
                LegislationItem(
                    header="Climate Action Initiative passed 38-7",
                    bullets=["City Council passed Bill 1 establishing a 65% GHG reduction target by 2030."],
                ),
                LegislationItem(
                    header="Affordable Housing Strategy requires 20% affordable units",
                    bullets=["Bill 2 passed 42-3, requiring 20% affordable units in large developments."],
                ),
            ]
        )

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": sample_legislation_notes}
        result = research_summary_writer(inputs)

        assert "legislation_summary" in result
        summary = result["legislation_summary"]
        assert summary is not None
        assert len(summary.items) == 2
        assert summary.items[0].header is not None
        assert summary.items[0].bullets is not None

    @patch("pipelines.node.summary_writer._get_model")
    def test_summary_writer_handles_no_content(
        self,
        mock_model: MagicMock,
    ):
        """Test that summary writer handles empty items gracefully."""
        mock_model.return_value.invoke.return_value = WriterOutput(items=[])

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": ""}
        result = research_summary_writer(inputs)

        assert "legislation_summary" in result
        assert result["legislation_summary"] is None


class TestSummaryQualityMetric:
    """Test suite for summary quality evaluation metric."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.metric = SummaryQualityMetric

    def test_high_quality_summary(self, mock_retrieval_context: str):
        """Test metric scores high for quality summary."""
        test_case = LLMTestCase(
            input="Summarize the legislation for Toronto",
            actual_output="""## ECONOMY & HOUSING

**Climate Action Initiative passed 38-7**
Toronto

City Council passed Bill 1 targeting 65% GHG reduction by 2030. The bill mandates building retrofits and allocates $50M for renewable energy investment.

**Affordable Housing Strategy requires 20% affordable units**
Toronto

Bill 2 passed 42-3, requiring 20% affordable units in new developments. It establishes a $100M housing trust and implements income-based rent control.""",
            retrieval_context=mock_retrieval_context,
        )

        self.metric.measure(test_case)
        assert self.metric.score >= 0.75
        assert self.metric.reason is not None

    def test_incomplete_summary(self, mock_retrieval_context: str):
        """Test metric detects incomplete summaries."""
        test_case = LLMTestCase(
            input="Summarize the legislation for Toronto",
            actual_output="""Summary:
- Climate bill passed
- Housing mentioned

(Only partial coverage, missing key details)""",
            retrieval_context=mock_retrieval_context,
        )

        self.metric.measure(test_case)
        assert self.metric.score < 0.8

    def test_biased_summary(self, mock_retrieval_context: str):
        """Test metric detects biased or editorialized summaries."""
        test_case = LLMTestCase(
            input="Summarize the legislation for Toronto",
            actual_output="""## Summary

The greedy developers will love this, but the climate bill is absolutely terrible and will destroy the economy!

- Climate Action: Bad for business
- Housing: Too little, too late from out-of-touch politicians

This legislation proves the council doesn't understand economics.""",
            retrieval_context=mock_retrieval_context,
        )

        self.metric.measure(test_case)
        assert self.metric.score < 0.5


class TestSchemaComplianceMetric:
    """Test suite for WriterOutput schema compliance validation."""

    def test_valid_schema_compliance(self):
        """Test that properly formatted output passes schema check."""
        metric = SchemaComplianceMetric()

        test_case = LLMTestCase(
            input="Summarize the legislation",
            actual_output="""## ECONOMY & HOUSING

**Council passes eviction package**
Toronto

The Council voted 48-18 to extend tenant protections to 1.6 million market-rate units.

**Albany advances FAB cap reform**
New York State

A-1234 heard in committee 12-4, lifting the 12.0 five-acre-minimum cap.""",
        )

        metric.measure(test_case)
        assert metric.score >= 0.8

    def test_missing_topic_header(self):
        """Test detection of missing topic header."""
        metric = SchemaComplianceMetric()

        test_case = LLMTestCase(
            input="Summarize the legislation",
            actual_output="""Some content without topic header or item structure.

Details:
- Point 1
- Point 2""",
        )

        metric.measure(test_case)
        assert metric.score < 1.0

    def test_missing_item_structure(self):
        """Test detection of missing item structure."""
        metric = SchemaComplianceMetric()

        test_case = LLMTestCase(
            input="Summarize the legislation",
            actual_output="""## ECONOMY & HOUSING

Just a paragraph of text without bold headers or item structure.""",
        )

        metric.measure(test_case)
        assert metric.score < 1.0


class TestSummaryWriterEdgeCases:
    """Edge case tests for summary writer."""

    @patch("pipelines.node.summary_writer._get_model")
    def test_very_long_notes(self, mock_model: MagicMock):
        """Test handling of very long input notes."""
        long_notes = "Point " * 1000

        mock_model.return_value.invoke.return_value = WriterOutput(
            items=[
                LegislationItem(
                    header=f"Point {i} summary",
                    bullets=[f"Details about point {i}."],
                )
                for i in range(5)
            ]
        )

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": long_notes}
        result = research_summary_writer(inputs)

        assert result["legislation_summary"] is not None

    @patch("pipelines.node.summary_writer._get_model")
    def test_unicode_content(self, mock_model: MagicMock):
        """Test handling of unicode characters."""
        mock_model.return_value.invoke.return_value = WriterOutput(
            items=[
                LegislationItem(
                    header="Cafe and Restaurant Regulations",
                    bullets=[
                        "New regulations for cafe outdoor seating in Toronto.",
                        "The rules cover patio permits and noise limits.",
                    ],
                )
            ]
        )

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": "Cafe regulations: Unicode content"}
        result = research_summary_writer(inputs)

        assert result["legislation_summary"] is not None
        assert "Cafe" in result["legislation_summary"].items[0].header

    @patch("pipelines.node.summary_writer._get_model")
    def test_empty_items_returns_none(self, mock_model: MagicMock):
        """Test that empty items list triggers None return."""
        mock_model.return_value.invoke.return_value = WriterOutput(items=[])

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": "Some notes"}
        result = research_summary_writer(inputs)

        assert result["legislation_summary"] is None

    @patch("pipelines.node.summary_writer._get_model")
    def test_none_response_returns_none(self, mock_model: MagicMock):
        """Test that None LLM response triggers None return."""
        mock_model.return_value.invoke.return_value = None

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": "Some notes"}
        result = research_summary_writer(inputs)

        assert result["legislation_summary"] is None


class TestMultiDimensionalSummaryMetric:
    """Test suite for multi-dimensional summary quality metric."""

    def test_metric_initialization(self):
        """Test that multi-dimensional metric initializes correctly."""
        from evals.metrics.summary_quality import MultiDimensionalSummaryMetric

        metric = MultiDimensionalSummaryMetric(
            factual_weight=0.5,
            completeness_weight=0.2,
            clarity_weight=0.15,
            objectivity_weight=0.15,
            threshold=0.75,
        )

        assert metric.factual_weight == 0.5
        assert metric.completeness_weight == 0.2
        assert metric.clarity_weight == 0.15
        assert metric.objectivity_weight == 0.15

    def test_custom_weight_configuration(self):
        """Test custom weight configuration."""
        from evals.metrics.summary_quality import MultiDimensionalSummaryMetric

        metric = MultiDimensionalSummaryMetric(
            factual_weight=0.6,
            completeness_weight=0.3,
            clarity_weight=0.05,
            objectivity_weight=0.05,
        )

        assert (
            metric.factual_weight
            + metric.completeness_weight
            + metric.clarity_weight
            + metric.objectivity_weight
            == 1.0
        )


def run_summary_writer_evaluation() -> dict[str, Any]:
    """Run full evaluation suite for summary writer.

    Returns:
        Dictionary with evaluation results
    """
    retrieval_context = """
    Source: Toronto City Council Official Website

    BILL 1-2024: CLIMATE ACTION INITIATIVE
    Passed: January 15, 2024 | Vote: 38-7
    - 65% GHG reduction by 2030
    - $50M renewable energy investment
    - Mandatory building retrofits

    BILL 2-2024: AFFORDABLE HOUSING STRATEGY
    Passed: January 22, 2024 | Vote: 42-3
    - 20% affordable units required
    - $100M housing trust
    - Income-based rent control
    """

    test_cases = [
        LLMTestCase(
            input="Summarize Toronto legislation for January 2024",
            actual_output="""## ECONOMY & HOUSING

**Climate Action Initiative passed 38-7**
Toronto

City Council passed Bill 1 establishing a 65% GHG reduction target by 2030. The bill mandates building retrofits and allocates $50M for renewable energy.

**Affordable Housing Strategy requires 20% affordable units**
Toronto

Bill 2 passed 42-3, requiring 20% affordable units in large developments. It establishes a $100M housing trust.""",
            retrieval_context=retrieval_context,
        ),
        LLMTestCase(
            input="Summarize Toronto legislation",
            actual_output="Some bills passed. Climate stuff. Housing maybe.",
            retrieval_context=retrieval_context,
        ),
    ]

    metrics = create_summary_quality_metric(
        threshold=0.75,
        multi_dimensional=True,
        include_schema_check=True,
    )

    results = evaluate(test_cases=test_cases, metrics=metrics)
    return results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
