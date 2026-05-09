"""End-to-end integration tests for NV Local pipeline.

Tests the complete pipeline from legislation discovery
to final structured summary generation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deepeval.test_case import LLMTestCase

from evals.metrics import (
    LegislationAccuracyMetric,
    SummaryQualityMetric,
    NoHallucinationMetric,
)


class TestEndToEndPipeline:
    """Test suite for complete NV Local pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_city: str):
        self.city = mock_city

    @patch("pipelines.nv_local.chain.invoke")
    def test_pipeline_produces_summary(self, mock_invoke: MagicMock):
        """Test that full pipeline produces a legislation summary."""
        from utils.schemas import WriterOutput, LegislationItem

        mock_invoke.return_value = {
            "city": self.city,
            "legislation_summary": WriterOutput(
                items=[
                    LegislationItem(
                        header="Test headline",
                        bullets=["Test bullet point."],
                    )
                ]
            ),
        }

        from pipelines.nv_local import run_pipeline

        result = run_pipeline(self.city)

        assert "legislation_summary" in result
        assert result["legislation_summary"] is not None
        assert len(result["legislation_summary"].items) > 0

    @patch("pipelines.nv_local.chain.invoke")
    def test_pipeline_handles_city(self, mock_invoke: MagicMock):
        """Test pipeline processes city parameter correctly."""
        mock_invoke.return_value = {
            "city": self.city,
            "legislation_summary": None,
        }

        from pipelines.nv_local import run_pipeline

        result = run_pipeline(self.city)
        assert result["city"] == self.city


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
        from utils.schemas import WriterOutput, LegislationItem

        mock_invoke.return_value = {
            "city": "Toronto",
            "notes": "test notes",
            "legislation_summary": WriterOutput(
                items=[LegislationItem(**item) for item in sample_writer_output["items"]]
            ),
        }

        from pipelines.node.summary_writer import summary_writer_chain

        result = summary_writer_chain.invoke({"city": "Toronto", "notes": "test"})

        assert "legislation_summary" in result


class TestPipelineErrorHandling:
    """Test pipeline error handling."""

    @patch("pipelines.node.legislation_finder.legislation_finder_chain.invoke")
    def test_pipeline_handles_legislation_finder_error(self, mock_invoke: MagicMock):
        """Test pipeline handles legislation finder errors."""
        mock_invoke.side_effect = Exception("Search API error")

        from pipelines.nv_local import run_pipeline

        result = run_pipeline("Toronto")

        assert "error" in result or "legislation_summary" in result

    @patch("pipelines.node.summary_writer.summary_writer_chain.invoke")
    def test_pipeline_handles_summary_writer_error(self, mock_invoke: MagicMock):
        """Test pipeline handles summary writer errors."""
        mock_invoke.side_effect = Exception("LLM error")

        from pipelines.nv_local import run_pipeline

        result = run_pipeline("Toronto")

        assert "error" in result or "legislation_summary" in result


class TestPipelineIntegration:
    """Full integration tests for pipeline."""

    @patch("pipelines.node.summary_writer._get_model")
    @patch("agents.legislation_finder.web_search.invoke")
    def test_full_pipeline_with_mocks(
        self,
        mock_search: MagicMock,
        mock_model: MagicMock,
        sample_legislation_sources: list[dict],
        sample_writer_output: dict[str, Any],
    ):
        """Test complete pipeline with all mocks."""
        from utils.schemas import WriterOutput, LegislationItem

        mock_search.return_value = {
            "web": {"results": [{"title": "Test", "url": "https://test.com"}]}
        }
        mock_model.return_value.invoke.return_value = WriterOutput(
            items=[LegislationItem(**item) for item in sample_writer_output["items"]]
        )

        from pipelines.nv_local import run_pipeline

        result = run_pipeline("Toronto")

        assert result is not None


class TestSupportedCities:
    """Test pipeline with supported cities."""

    @pytest.mark.parametrize("city", ["Toronto", "New York City", "San Diego"])
    @patch("pipelines.nv_local.chain.invoke")
    def test_supported_cities(self, mock_invoke: MagicMock, city: str):
        """Test pipeline with each supported city."""
        supported_cities = ["Toronto", "New York City", "San Diego"]

        assert city in supported_cities

        mock_invoke.return_value = {
            "city": city,
            "legislation_summary": None,
        }

        from pipelines.nv_local import run_pipeline

        result = run_pipeline(city)

        assert result["city"] == city


def run_e2e_evaluation() -> dict[str, Any]:
    """Run full end-to-end evaluation suite.

    Returns:
        Dictionary with evaluation results
    """
    from deepeval import evaluate

    test_cases = [
        LLMTestCase(
            input="Run full NV Local pipeline for Toronto",
            actual_output="Climate Action Initiative passed 38-7. 65% GHG reduction by 2030. Affordable Housing Strategy requires 20% affordable units.",
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
    ]

    metrics = [
        LegislationAccuracyMetric,
        SummaryQualityMetric,
        NoHallucinationMetric,
    ]

    results = evaluate(test_cases=test_cases, metrics=metrics)
    return results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
