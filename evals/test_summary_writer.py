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
from utils.schemas import WriterOutput


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
            title="Test Title",
            summary="Test summary",
            body="Test body content",
        )

        assert valid_output.title == "Test Title"
        assert valid_output.summary == "Test summary"
        assert valid_output.body == "Test body content"

    def test_writer_output_optional_fields(self):
        """Test WriterOutput handles optional fields correctly."""
        minimal_output = WriterOutput()

        assert minimal_output.title is None
        assert minimal_output.summary is None
        assert minimal_output.body is None

    @patch("pipelines.node.summary_writer._get_model")
    def test_summary_writer_produces_valid_schema(
        self,
        mock_model: MagicMock,
        sample_legislation_notes: str,
    ):
        """Test that summary writer produces valid WriterOutput."""
        mock_model.return_value.invoke.return_value = WriterOutput(
            title="Toronto Legislation Update",
            summary="City Council passed climate and housing legislation.",
            body="- Climate Action: 65% GHG reduction\n- Housing: 20% affordable units",
        )

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": sample_legislation_notes}
        result = research_summary_writer(inputs)

        assert "legislation_summary" in result
        summary = result["legislation_summary"]
        assert summary is not None
        assert summary.title is not None
        assert summary.summary is not None
        assert summary.body is not None

    @patch("pipelines.node.summary_writer._get_model")
    def test_summary_writer_handles_no_content(
        self,
        mock_model: MagicMock,
    ):
        """Test that summary writer handles empty notes gracefully."""
        mock_model.return_value.invoke.return_value = WriterOutput(
            title="No Content",
            summary=None,
            body=None,
        )

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": ""}
        result = research_summary_writer(inputs)

        assert "legislation_summary" in result


class TestSummaryQualityMetric:
    """Test suite for summary quality evaluation metric."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.metric = SummaryQualityMetric

    def test_high_quality_summary(self, mock_retrieval_context: str):
        """Test metric scores high for quality summary."""
        test_case = LLMTestCase(
            input="Summarize the legislation for Toronto",
            actual_output="""## Toronto City Council Legislation Update

### Summary
City Council passed two major bills: Climate Action Initiative (Bill 1) targeting 65% GHG reduction by 2030, and Affordable Housing Strategy (Bill 2) requiring 20% affordable units in new developments.

### Key Points
- **Climate Bill (Bill 1)**: Passed 38-7, $50M renewable energy investment
- **Housing Bill (Bill 2)**: Passed 42-3, $100M housing trust established
- Both bills align with council priorities for 2024""",
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
            actual_output="""# Title of Legislation

## Summary
Brief 1-2 sentence summary of the legislation.

## Details
- Point 1
- Point 2
- Point 3""",
        )

        metric.measure(test_case)
        assert metric.score >= 0.8

    def test_missing_title(self):
        """Test detection of missing title."""
        metric = SchemaComplianceMetric()

        test_case = LLMTestCase(
            input="Summarize the legislation",
            actual_output="""Summary of legislation content here.

Details:
- Point 1
- Point 2""",
        )

        metric.measure(test_case)
        assert metric.score < 1.0

    def test_missing_body(self):
        """Test detection of missing body."""
        metric = SchemaComplianceMetric()

        test_case = LLMTestCase(
            input="Summarize the legislation",
            actual_output="""# Title of Legislation

## Summary
Brief summary of the legislation.""",
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
            title="Long Document Summary",
            summary="Concise summary of lengthy content.",
            body="- " + "\n- ".join([f"Point {i}" for i in range(50)]),
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
            title="Café and Restaurant Regulations",
            summary="New regulations for café outdoor seating in Toronto.",
            body="- Unicode: café, naïve, résumé\n- Special chars: © ® ™",
        )

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        inputs: ChainData = {"notes": "Café regulations: Unicode content"}
        result = research_summary_writer(inputs)

        assert result["legislation_summary"] is not None
        assert "café" in result["legislation_summary"].title.lower()

    @patch("pipelines.node.summary_writer._get_model")
    def test_no_legislation_patterns(self, mock_model: MagicMock):
        """Test that 'no legislation' patterns are handled."""
        no_content_patterns = [
            "No Content",
            "No Recent Legislation",
            "None",
            "N/A",
            "no recent legislation found",
        ]

        from pipelines.node.summary_writer import research_summary_writer
        from utils.schemas import ChainData

        for pattern in no_content_patterns:
            mock_model.return_value.invoke.return_value = WriterOutput(
                title=pattern,
                summary="No content",
                body="No body",
            )

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
            actual_output="""# Toronto City Council Legislation Update

## Summary
City Council passed two significant bills: Climate Action Initiative (Bill 1) establishing 65% GHG reduction target and Affordable Housing Strategy (Bill 2) requiring 20% affordable units in new developments.

## Full Report
- **Climate Action Initiative (Bill 1)**: Passed 38-7, 65% GHG reduction by 2030, $50M renewable investment
- **Affordable Housing Strategy (Bill 2)**: Passed 42-3, 20% affordable units, $100M housing trust
- Both bills represent major council priorities for 2024""",
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
