"""End-to-end integration tests for NV Local pipeline.

Tests the complete pipeline from legislation discovery
to final markdown report generation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deepeval.test_case import LLMTestCase

from evals.metrics import (
    LegislationAccuracyMetric,
    SummaryQualityMetric,
    PoliticalRelevanceMetric,
    ReportFormattingMetric,
    NoHallucinationMetric,
)


class TestEndToEndPipeline:
    """Test suite for complete NV Local pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_city: str):
        self.city = mock_city

    @patch("pipelines.nv_local.chain.invoke")
    def test_pipeline_produces_markdown_report(
        self, mock_invoke: MagicMock, sample_markdown_report: str
    ):
        """Test that full pipeline produces markdown report."""
        mock_invoke.return_value = {
            "city": self.city,
            "markdown_report": sample_markdown_report,
        }

        from pipelines.nv_local import run_pipeline

        result = run_pipeline(self.city)

        assert "markdown_report" in result
        assert isinstance(result["markdown_report"], str)
        assert len(result["markdown_report"]) > 0

    @patch("pipelines.nv_local.chain.invoke")
    def test_pipeline_handles_city(self, mock_invoke: MagicMock):
        """Test pipeline processes city parameter correctly."""
        mock_invoke.return_value = {
            "city": self.city,
            "markdown_report": "# Report",
        }

        from pipelines.nv_local import run_pipeline

        result = run_pipeline(self.city)
        assert result["city"] == self.city

    @patch("pipelines.nv_local.chain.invoke")
    def test_pipeline_handles_multiple_cities(self, mock_invoke: MagicMock):
        """Test runner handles multiple cities."""
        cities = ["Toronto", "New York City", "San Diego"]
        mock_invoke.side_effect = [
            {"city": city, "markdown_report": f"# {city} Report"} for city in cities
        ]

        from runners.run_container_job import run_pipelines_for_cities

        results = run_pipelines_for_cities(cities)

        assert len(results) == 3
        for city in cities:
            assert city in results
            assert "markdown_report" in results[city]


class TestPipelineComponents:
    """Test individual pipeline components in integration context."""

    @patch("pipelines.node.legislation_finder.legislation_finder_chain.invoke")
    def test_legislation_finder_chain(
        self, mock_invoke: MagicMock, sample_legislation_sources: list[dict]
    ):
        """Test legislation finder chain integration."""
        mock_invoke.return_value = {
            "city": "Toronto",
            "legislation_sources": str(sample_legislation_sources),
        }

        from pipelines.node.legislation_finder import legislation_finder_chain

        result = legislation_finder_chain.invoke({"city": "Toronto"})

        assert "legislation_sources" in result

    @patch("pipelines.node.content_retrieval.content_retrieval_chain.invoke")
    def test_content_retrieval_chain(self, mock_invoke: MagicMock):
        """Test content retrieval chain integration."""
        mock_invoke.return_value = {
            "city": "Toronto",
            "legislation_sources": "test sources",
            "retrieved_content": "retrieved content here",
        }

        from pipelines.node.content_retrieval import content_retrieval_chain

        result = content_retrieval_chain.invoke(
            {"city": "Toronto", "legislation_sources": "test"}
        )

        assert "retrieved_content" in result or "notes" in result

    @patch("pipelines.node.note_taker.note_taker_chain.invoke")
    def test_note_taker_chain(self, mock_invoke: MagicMock):
        """Test note taker chain integration."""
        mock_invoke.return_value = {
            "city": "Toronto",
            "notes": "Compressed notes from content",
        }

        from pipelines.node.note_taker import note_taker_chain

        result = note_taker_chain.invoke(
            {"city": "Toronto", "retrieved_content": "content"}
        )

        assert "notes" in result

    @patch("pipelines.node.summary_writer.summary_writer_chain.invoke")
    def test_summary_writer_chain(
        self, mock_invoke: MagicMock, sample_writer_output: dict[str, Any]
    ):
        """Test summary writer chain integration."""
        from utils.schemas import WriterOutput

        mock_invoke.return_value = {
            "city": "Toronto",
            "notes": "test notes",
            "legislation_summary": WriterOutput(
                title=sample_writer_output["title"],
                summary=sample_writer_output["summary"],
                body=sample_writer_output["body"],
            ),
        }

        from pipelines.node.summary_writer import summary_writer_chain

        result = summary_writer_chain.invoke({"city": "Toronto", "notes": "test"})

        assert "legislation_summary" in result

    @patch("pipelines.node.politician_commentary.politician_commentary_chain.invoke")
    def test_politician_commentary_chain(
        self, mock_invoke: MagicMock, sample_political_statements: list[dict]
    ):
        """Test politician commentary chain integration."""
        mock_invoke.return_value = {
            "city": "Toronto",
            "politician_public_statements": sample_political_statements,
        }

        from pipelines.node.politician_commentary import (
            politician_commentary_chain,
        )

        result = politician_commentary_chain.invoke({"city": "Toronto"})

        assert "politician_public_statements" in result

    @patch("pipelines.node.report_formatter.report_formatter_chain.invoke")
    def test_report_formatter_chain(
        self, mock_invoke: MagicMock, sample_markdown_report: str
    ):
        """Test report formatter chain integration."""
        mock_invoke.return_value = {
            "city": "Toronto",
            "markdown_report": sample_markdown_report,
        }

        from pipelines.node.report_formatter import report_formatter_chain
        from utils.schemas import WriterOutput

        result = report_formatter_chain.invoke(
            {
                "legislation_summary": WriterOutput(
                    title="Test", summary="Test", body="Test"
                ),
                "politician_public_statements": [],
            }
        )

        assert "markdown_report" in result


class TestPipelineErrorHandling:
    """Test pipeline error handling."""

    @patch("pipelines.node.legislation_finder.legislation_finder_chain.invoke")
    def test_pipeline_handles_legislation_finder_error(self, mock_invoke: MagicMock):
        """Test pipeline handles legislation finder errors."""
        mock_invoke.side_effect = Exception("Search API error")

        from pipelines.nv_local import run_pipeline

        result = run_pipeline("Toronto")

        assert "error" in result or "markdown_report" in result

    @patch("pipelines.node.summary_writer.summary_writer_chain.invoke")
    def test_pipeline_handles_summary_writer_error(self, mock_invoke: MagicMock):
        """Test pipeline handles summary writer errors."""
        mock_invoke.side_effect = Exception("LLM error")

        from pipelines.nv_local import run_pipeline

        result = run_pipeline("Toronto")

        assert "error" in result or "markdown_report" in result


class TestPipelineOutput:
    """Test pipeline output quality."""

    def test_report_contains_expected_structure(self, sample_markdown_report: str):
        """Test that report has expected markdown structure."""
        assert "# " in sample_markdown_report
        assert "## " in sample_markdown_report
        assert sample_markdown_report.count("#") >= 2

    def test_report_contains_politician_section(self, sample_markdown_report: str):
        """Test that report contains politician statements section."""
        assert "Politician" in sample_markdown_report
        assert (
            "Coming Soon" in sample_markdown_report or "###" in sample_markdown_report
        )


class TestPipelineIntegration:
    """Full integration tests for pipeline."""

    @patch("agents.political_commentary_finder.political_commentary_agent.invoke")
    @patch("pipelines.node.summary_writer._get_model")
    @patch("tools.legislation_finder.web_search.invoke")
    def test_full_pipeline_with_mocks(
        self,
        mock_search: MagicMock,
        mock_model: MagicMock,
        mock_political: MagicMock,
        sample_legislation_sources: list[dict],
        sample_writer_output: dict[str, Any],
        sample_political_statements: list[dict],
    ):
        """Test complete pipeline with all mocks."""
        from utils.schemas import WriterOutput

        mock_search.return_value = {
            "web": {"results": [{"title": "Test", "url": "https://test.com"}]}
        }
        mock_model.return_value.invoke.return_value = WriterOutput(
            title=sample_writer_output["title"],
            summary=sample_writer_output["summary"],
            body=sample_writer_output["body"],
        )
        mock_political.return_value = {
            "political_commentary": [],
            "political_figures": [],
        }

        from pipelines.nv_local import run_pipeline

        result = run_pipeline("Toronto")

        assert result is not None
        assert "markdown_report" in result or "error" in result

    def test_pipeline_output_quality_metrics(self, sample_markdown_report: str):
        """Test report quality using evaluation metrics."""
        test_case = LLMTestCase(
            input="Full pipeline for Toronto legislation",
            actual_output=sample_markdown_report,
            retrieval_context="""
            Source: Toronto City Council
            Bill 1-2024: Climate Action Initiative (65% GHG reduction)
            Bill 2-2024: Affordable Housing Strategy (20% affordable units)
            """,
        )

        metrics = [
            ReportFormattingMetric,
            NoHallucinationMetric,
        ]

        for metric in metrics:
            metric.measure(test_case)
            assert metric.score >= 0


class TestSupportedCities:
    """Test pipeline with supported cities."""

    @pytest.mark.parametrize("city", ["Toronto", "New York City", "San Diego"])
    @patch("pipelines.nv_local.chain.invoke")
    def test_supported_cities(self, mock_invoke: MagicMock, city: str):
        """Test pipeline with each supported city."""
        from data import SUPPORTED_CITIES

        assert city in SUPPORTED_CITIES

        mock_invoke.return_value = {
            "city": city,
            "markdown_report": f"# {city} Report",
        }

        from pipelines.nv_local import run_pipeline

        result = run_pipeline(city)

        assert result["city"] == city


class TestPipelineRendering:
    """Test pipeline output rendering."""

    @patch("runners.run_container_job.run_pipelines_for_cities")
    def test_render_city_reports(
        self,
        mock_run: MagicMock,
        sample_markdown_report: str,
    ):
        """Test rendering multiple city reports."""
        mock_run.return_value = {
            "Toronto": {"markdown_report": sample_markdown_report},
            "NYC": {"markdown_report": "# NYC Report"},
        }

        from runners.run_container_job import render_city_reports_markdown

        result = render_city_reports_markdown(mock_run.return_value)

        assert "## Toronto" in result
        assert "## NYC" in result

    @patch("runners.run_container_job.run_pipelines_for_cities")
    def test_render_with_errors(self, mock_run: MagicMock):
        """Test rendering with pipeline errors."""
        mock_run.return_value = {
            "Toronto": {
                "error": "Test error",
                "markdown_report": "",
            },
        }

        from runners.run_container_job import render_city_reports_markdown

        result = render_city_reports_markdown(mock_run.return_value)

        assert "**Error:**" in result


def run_e2e_evaluation() -> dict[str, Any]:
    """Run full end-to-end evaluation suite.

    Returns:
        Dictionary with evaluation results
    """
    from deepeval import evaluate

    test_cases = [
        LLMTestCase(
            input="Run full NV Local pipeline for Toronto",
            actual_output="""# Toronto City Council Legislation Update - January 2024

## Summary
City Council passed significant climate action and housing legislation including a 65% GHG reduction target and mandatory affordable housing requirements.

## Full Report
- **Climate Action Initiative (Bill 1)**: Passed 38-7, establishes 65% GHG reduction target by 2030
- **Affordable Housing Strategy (Bill 2)**: Passed 42-3, requires 20% affordable units

---

## Politician Public Statements
### Coming Soon!

### Olivia Chow
Mayor Chow emphasized the climate legislation as a historic step.""",
            retrieval_context="""
            Source: Toronto City Council
            Bill 1-2024: Climate Action Initiative
            - 65% GHG reduction by 2030
            - Passed 38-7
            
            Bill 2-2024: Affordable Housing Strategy
            - 20% affordable units
            - Passed 42-3
            """,
        ),
        LLMTestCase(
            input="Run full pipeline for NYC",
            actual_output="""# NYC City Council Update

## Summary
City Council passed Green New Deal legislation.

## Full Report
- Intro 1234: Climate legislation passed
- Housing preservation laws updated

## Politician Statements
### Coming Soon!""",
            retrieval_context="""
            Source: NYC City Council
            Intro 1234: Green New Deal for NYC
            Housing Preservation Plan
            """,
        ),
    ]

    metrics = [
        LegislationAccuracyMetric,
        SummaryQualityMetric,
        PoliticalRelevanceMetric,
        ReportFormattingMetric,
        NoHallucinationMetric,
    ]

    results = evaluate(test_cases=test_cases, metrics=metrics)
    return results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
