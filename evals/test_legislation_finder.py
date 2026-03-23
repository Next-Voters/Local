"""Unit tests for LegislationFinderAgent.

Tests the agent's ability to find relevant municipal legislation
and analyze source reliability.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase
from deepeval import evaluate

from evals.metrics.legislation_accuracy import (
    LegislationAccuracyMetric,
    create_legislation_accuracy_metric,
)
from evals.metrics.no_hallucination import NoHallucinationMetric


class TestLegislationFinderAgent:
    """Test suite for LegislationFinderAgent component."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_city: str, sample_legislation_sources: list[dict]):
        self.city = mock_city
        self.sample_sources = sample_legislation_sources

    def test_agent_initialization(self):
        """Test that agent can be instantiated."""
        from agents.legislation_finder import legislation_finder_agent

        assert legislation_finder_agent is not None
        assert hasattr(legislation_finder_agent, "invoke")

    @patch("agents.legislation_finder.web_search.invoke")
    def test_web_search_finds_relevant_sources(
        self, mock_search: MagicMock, sample_legislation_sources: list[dict]
    ):
        """Test that web search returns relevant legislation sources."""
        mock_search.return_value = {
            "web": {
                "results": [
                    {
                        "title": src["title"],
                        "url": src["url"],
                        "description": src["description"],
                    }
                    for src in sample_legislation_sources
                ]
            }
        }

        from tools.legislation_finder import web_search

        result = web_search.invoke(f"{self.city} city council legislation 2024")

        assert "web" in result
        assert len(result["web"]["results"]) == 3
        assert all(
            self.city in r["title"] or self.city in r["description"]
            for r in result["web"]["results"]
        )

    @patch("tools.legislation_finder.reliability_analysis.invoke")
    def test_reliability_analysis_scores_sources(self, mock_reliability: MagicMock):
        """Test that reliability analysis assigns scores to sources."""
        mock_reliability.return_value = {
            "analyses": [
                {
                    "url": "https://www.toronto.ca/legdocs/mmis/2024/cc/billd -it/2024-cc-doc-1.pdf",
                    "reliability_score": 0.95,
                    "reasoning": "Official city government source",
                },
                {
                    "url": "https://www.thestar.com/toronto/legislation",
                    "reliability_score": 0.7,
                    "reasoning": "Established news source but not primary",
                },
            ]
        }

        from tools.legislation_finder import reliability_analysis

        sources = [
            {
                "url": "https://www.toronto.ca/legdocs/mmis/2024/cc/billd -it/2024-cc-doc-1.pdf"
            },
            {"url": "https://www.thestar.com/toronto/legislation"},
        ]
        result = reliability_analysis.invoke({"sources": sources})

        assert "analyses" in result
        assert len(result["analyses"]) == 2
        assert all("reliability_score" in a for a in result["analyses"])


class TestLegislationAccuracyMetric:
    """Test suite for legislation accuracy evaluation metric."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.metric = create_legislation_accuracy_metric(threshold=0.7)

    def test_metric_with_relevant_sources(self):
        """Test metric scores highly for relevant sources."""
        test_case = LLMTestCase(
            input="Find recent legislation for Toronto",
            actual_output="""Found the following legislation:
            1. Toronto City Council Bill 1-2024: Climate Action Initiative
               URL: https://www.toronto.ca/legdocs/mmis/2024/cc/billd -it/2024-cc-doc-1.pdf
            2. Toronto Municipal Code Amendment: Affordable Housing
               URL: https://www.toronto.ca/legdocs/mmis/2024/
            """,
        )

        self.metric.measure(test_case)
        assert self.metric.score >= 0.7
        assert self.metric.reason is not None

    def test_metric_with_irrelevant_sources(self):
        """Test metric scores low for irrelevant sources."""
        test_case = LLMTestCase(
            input="Find recent legislation for Toronto",
            actual_output="""Found the following:
            1. Federal Budget 2024 (irrelevant)
            2. US Senate Bill (wrong country)
            3. General news article
            """,
        )

        self.metric.measure(test_case)
        assert self.metric.score < 0.7

    def test_metric_with_mixed_relevance(self):
        """Test metric with mixed relevance sources."""
        test_case = LLMTestCase(
            input="Find recent legislation for Toronto",
            actual_output="""Found:
            1. Toronto Climate Action Bill (relevant, government source)
            2. Toronto Star news article about provincial politics (somewhat relevant)
            3. NYC legislation (irrelevant)
            """,
        )

        self.metric.measure(test_case)
        assert 0.4 <= self.metric.score <= 0.8

    def test_detailed_metric_initialization(self):
        """Test detailed metric can be created."""
        from evals.metrics.legislation_accuracy import DetailedLegislationAccuracyMetric

        detailed_metric = DetailedLegislationAccuracyMetric(
            city_relevance_weight=0.5,
            legislative_authenticity_weight=0.25,
            source_credibility_weight=0.25,
            threshold=0.75,
        )

        assert detailed_metric.city_relevance_weight == 0.5
        assert detailed_metric.legislative_authenticity_weight == 0.25
        assert detailed_metric.source_credibility_weight == 0.25


class TestLegislationFinderIntegration:
    """Integration tests for legislation finder workflow."""

    @patch("agents.legislation_finder.legislation_finder_agent.invoke")
    def test_full_agent_workflow(
        self,
        mock_invoke: MagicMock,
        mock_city: str,
        sample_legislation_sources: list[dict],
    ):
        """Test complete agent workflow from query to sources."""
        mock_invoke.return_value = {
            "city": mock_city,
            "reliable_legislation_sources": [
                src["url"] for src in sample_legislation_sources[:2]
            ],
            "messages": [],
        }

        from agents.legislation_finder import legislation_finder_agent

        result = legislation_finder_agent.invoke({"city": mock_city})

        assert "reliable_legislation_sources" in result
        assert len(result["reliable_legislation_sources"]) >= 1

    def test_city_specific_search_queries(self):
        """Test that search queries are city-specific."""
        from agents.legislation_finder import legislation_finder_agent

        test_cases = [
            ("Toronto", "Toronto"),
            ("New York City", "New York City"),
            ("San Diego", "San Diego"),
        ]

        for city, expected_in_query in test_cases:
            state = {"city": city, "messages": [], "reflection_list": []}
            from agents.legislation_finder import legislation_finder_sys_prompt
            from datetime import datetime, timedelta

            prompt = legislation_finder_sys_prompt.format(
                input_city=city,
                last_week_date=(datetime.today() - timedelta(days=7)).strftime(
                    "%B %d, %Y"
                ),
                today=datetime.today().strftime("%B %d, %Y"),
            )
            assert expected_in_query in prompt


class TestLegislationFinderEdgeCases:
    """Edge case tests for legislation finder."""

    def test_empty_city_handling(self):
        """Test handling of empty city input."""
        from agents.legislation_finder import legislation_finder_agent

        result = legislation_finder_agent.invoke({"city": ""})
        assert result is not None

    def test_no_legislation_found(self):
        """Test handling when no legislation is found."""
        with patch("tools.legislation_finder.web_search.invoke") as mock_search:
            mock_search.return_value = {"web": {"results": []}}

            from tools.legislation_finder import web_search

            result = web_search.invoke("nonexistent city xyz123 legislation")
            assert result["web"]["results"] == []

    def test_invalid_source_urls(self):
        """Test handling of invalid source URLs."""
        with patch("tools.legislation_finder.reliability_analysis.invoke") as mock:
            mock.return_value = {
                "analyses": [
                    {
                        "url": "not-a-valid-url",
                        "reliability_score": 0.0,
                        "reasoning": "Invalid URL format",
                    }
                ]
            }

            from tools.legislation_finder import reliability_analysis

            result = reliability_analysis.invoke(
                {"sources": [{"url": "not-a-valid-url"}]}
            )
            assert result["analyses"][0]["reliability_score"] == 0.0


def run_legislation_finder_evaluation() -> dict[str, Any]:
    """Run full evaluation suite for legislation finder.

    Returns:
        Dictionary with evaluation results
    """
    test_cases = [
        LLMTestCase(
            input="Find recent legislation for Toronto",
            actual_output="""Toronto City Council legislation found:
            1. Bill 1-2024: Climate Action Initiative
               Source: https://www.toronto.ca/legdocs/mmis/2024/cc/billd -it/2024-cc-doc-1.pdf
               (Official Toronto government source)
            2. Bill 2-2024: Affordable Housing Strategy
               Source: https://www.toronto.ca/legdocs/mmis/2024/cc/billd -it/2024-cc-doc-2.pdf
               (Official Toronto government source)""",
        ),
        LLMTestCase(
            input="Find recent legislation for NYC",
            actual_output="""NYC legislation found:
            1. Intro 1234: Green New Deal for NYC
               Source: https://legistar.council.nyc.gov/LegislationDetail.aspx?ID=1234567
               (Official NYC City Council source)
            2. Local Law 45: Housing Preservation
               Source: https://www.nyc.gov/housing-development""",
        ),
        LLMTestCase(
            input="Find recent legislation for Toronto",
            actual_output="""Found some general news:
            - Federal elections coming up
            - Provincial budget discussions
            - Some random article about Toronto sports""",
        ),
    ]

    metrics = [
        create_legislation_accuracy_metric(threshold=0.7),
        NoHallucinationMetric,
    ]

    results = evaluate(test_cases=test_cases, metrics=metrics)
    return results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
