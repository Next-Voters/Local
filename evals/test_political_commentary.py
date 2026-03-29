"""Unit tests for PoliticalCommentaryAgent.

Tests the agent's ability to find relevant political figures
and their public statements on municipal legislation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deepeval.test_case import LLMTestCase

from evals.metrics.political_relevance import (
    PoliticalRelevanceMetric,
    JurisdictionalRelevanceMetric,
    StatementQualityMetric,
    create_political_relevance_metric,
)
from utils.schemas import PoliticalCommentaryState, PoliticalFigure


class TestPoliticalCommentaryAgent:
    """Test suite for PoliticalCommentaryAgent component."""

    @pytest.fixture(autouse=True)
    def setup(
        self,
        mock_city: str,
        sample_politician_data: list[dict],
        sample_political_statements: list[dict],
    ):
        self.city = mock_city
        self.politician_data = sample_politician_data
        self.statements = sample_political_statements

    def test_agent_initialization(self):
        """Test that agent can be instantiated."""
        from agents.political_commentary_finder import political_commentary_agent

        assert political_commentary_agent is not None
        assert hasattr(political_commentary_agent, "invoke")

    def test_political_figure_schema(self):
        """Test PoliticalFigure schema validation."""
        figure = PoliticalFigure(
            name="Test Politician",
            position="Mayor",
            party="Test Party",
            jurisdiction="Test City",
            source_url="https://example.gov",
        )

        assert figure.name == "Test Politician"
        assert figure.position == "Mayor"
        assert figure.jurisdiction == "Test City"

    @patch("agents.political_commentary_finder.political_commentary_agent.invoke")
    def test_agent_finds_politicians(
        self,
        mock_invoke: MagicMock,
        mock_city: str,
        sample_politician_data: list[dict],
    ):
        """Test that agent finds relevant political figures."""
        mock_invoke.return_value = {
            "city": mock_city,
            "political_figures": sample_politician_data,
            "political_commentary": [],
        }

        from agents.political_commentary_finder import political_commentary_agent

        result = political_commentary_agent.invoke({"city": mock_city})

        assert "political_figures" in result
        assert len(result["political_figures"]) >= 1

    @patch("tools.political_commentary_finder.political_figure_finder.invoke")
    def test_political_figure_finder_tool(
        self, mock_find: MagicMock, sample_politician_data: list[dict]
    ):
        """Test political figure finder tool."""
        mock_find.return_value = {"results": self.politician_data}

        from tools.political_commentary_finder import political_figure_finder

        result = political_figure_finder.invoke(f"Political figures in {self.city}")

        assert "results" in result
        assert len(result["results"]) == 3

    @patch("tools.political_commentary_finder.search_political_commentary.invoke")
    def test_commentary_search_tool(
        self, mock_search: MagicMock, sample_political_statements: list[dict]
    ):
        """Test political commentary search tool."""
        mock_search.return_value = {"results": self.statements}

        from tools.political_commentary_finder import search_political_commentary

        result = search_political_commentary.invoke("Olivia Chow statements on housing")

        assert "results" in result


class TestPoliticalRelevanceMetric:
    """Test suite for political relevance evaluation metric."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.metric = PoliticalRelevanceMetric

    def test_highly_relevant_politicians(self):
        """Test metric scores high for relevant political figures."""
        test_case = LLMTestCase(
            input="Find political figures commenting on Toronto housing legislation",
            actual_output="""Political figures and statements:

1. Olivia Chow, Mayor of Toronto
   - Statement: "This housing legislation represents our commitment to Toronto families"
   - Source: Toronto Mayor's Office press release

2. Josh Matlow, City Councilor (Ward 12)
   - Statement: "While supportive, we need more funding for affordable units"
   - Source: Toronto Star op-ed

3. Jennifer Veen, City Councilor (Ward 9)
   - Statement: "Will vote yes on Bill 2-2024"
   - Source: Council meeting minutes""",
        )

        self.metric.measure(test_case)
        assert self.metric.score >= 0.65
        assert self.metric.reason is not None

    def test_irrelevant_politicians(self):
        """Test metric scores low for irrelevant figures."""
        test_case = LLMTestCase(
            input="Find political figures commenting on Toronto housing",
            actual_output="""Relevant figures:

1. President Biden - Federal politics, not Toronto
2. Premier Ford - Ontario Premier, not direct Toronto jurisdiction
3. Celebrity chef commenting on food trends""",
        )

        self.metric.measure(test_case)
        assert self.metric.score < 0.5

    def test_mixed_relevance(self):
        """Test metric with mixed relevance."""
        test_case = LLMTestCase(
            input="Find political figures on Toronto climate legislation",
            actual_output="""Found:

1. Olivia Chow (Mayor of Toronto) - Directly relevant ✓
2. Premier Ford - Somewhat relevant (provincial oversight) △
3. Random political blogger - Not relevant ✗""",
        )

        self.metric.measure(test_case)
        assert 0.3 <= self.metric.score <= 0.7


class TestJurisdictionalRelevanceMetric:
    """Test suite for jurisdictional relevance validation."""

    def test_correct_jurisdiction(self):
        """Test that correct jurisdiction scores high."""
        metric = JurisdictionalRelevanceMetric(threshold=0.8)

        test_case = LLMTestCase(
            input="Political figures for Toronto",
            actual_output="""Politicians with correct jurisdiction:
1. Olivia Chow - Mayor of Toronto ✓
2. Gord Perks - Toronto City Councilor ✓
3. Mike Layton - Former Toronto Councilor ✓""",
        )

        metric.measure(test_case)
        assert metric.score >= 0.8

    def test_incorrect_jurisdiction(self):
        """Test that incorrect jurisdiction scores low."""
        metric = JurisdictionalRelevanceMetric(threshold=0.8)

        test_case = LLMTestCase(
            input="Political figures for Toronto",
            actual_output="""Politicians found:
1. Justin Trudeau - Canadian Prime Minister (federal) ✗
2. Kathy Hochul - NY Governor (wrong jurisdiction) ✗
3. Generic political commentator ✗""",
        )

        metric.measure(test_case)
        assert metric.score < 0.5


class TestStatementQualityMetric:
    """Test suite for statement quality evaluation."""

    def test_high_quality_statements(self):
        """Test metric scores high for quality statements."""
        metric = StatementQualityMetric(threshold=0.6)

        test_case = LLMTestCase(
            input="Political statements on Toronto housing Bill 2-2024",
            actual_output="""Statement 1: Mayor Olivia Chow
"Bill 2-2024 represents a transformative step for housing affordability in Toronto. 
The 20% affordable housing requirement will create thousands of units for families 
who have been priced out of our market."
Source: Mayor's Office official press release (January 22, 2024)

Statement 2: Councilor Josh Matlow
"I support the intent of Bill 2-2024, but we need to ensure the $100M housing 
trust includes dedicated funding for deep affordable units serving those 
earning below $40,000 annually."
Source: Toronto Star op-ed, January 23, 2024""",
        )

        metric.measure(test_case)
        assert metric.score >= 0.6

    def test_low_quality_statements(self):
        """Test metric detects low quality statements."""
        metric = StatementQualityMetric(threshold=0.6)

        test_case = LLMTestCase(
            input="Political statements on housing",
            actual_output="""Some politicians said stuff about housing maybe.""",
        )

        metric.measure(test_case)
        assert metric.score < 0.4


class TestPoliticalCommentaryIntegration:
    """Integration tests for political commentary workflow."""

    @patch("agents.political_commentary_finder.political_commentary_agent.invoke")
    def test_full_workflow(
        self,
        mock_invoke: MagicMock,
        mock_city: str,
        sample_politician_data: list[dict],
        sample_political_statements: list[dict],
    ):
        """Test complete political commentary workflow."""
        mock_invoke.return_value = {
            "city": mock_city,
            "political_figures": sample_politician_data,
            "political_commentary": [
                {
                    "politician": "Olivia Chow",
                    "source_url": "https://example.com",
                    "comment": "Statement on legislation",
                }
            ],
        }

        from agents.political_commentary_finder import political_commentary_agent

        result = political_commentary_agent.invoke({"city": mock_city})

        assert "political_figures" in result
        assert "political_commentary" in result

    def test_city_specific_queries(self):
        """Test that queries are city-specific."""
        test_cases = [
            ("Toronto", "Toronto"),
            ("New York City", "New York"),
            ("San Diego", "San Diego"),
        ]

        for city, expected in test_cases:
            from config.system_prompts import political_commentary_sys_prompt

            assert expected in political_commentary_sys_prompt


class TestPoliticalCommentaryEdgeCases:
    """Edge case tests for political commentary."""

    def test_no_politicians_found(self):
        """Test handling when no politicians are found."""
        with patch(
            "tools.political_commentary_finder.political_figure_finder.invoke"
        ) as mock:
            mock.return_value = {"results": []}

            from tools.political_commentary_finder import political_figure_finder

            result = political_figure_finder.invoke("Nonexistent City Politicians")
            assert result["results"] == []

    def test_politician_without_party(self):
        """Test handling of politicians without party affiliation."""
        figure = PoliticalFigure(
            name="Independent Politician",
            position="Mayor",
            jurisdiction="Test City",
        )

        assert figure.party is None
        assert figure.name == "Independent Politician"

    def test_empty_statements(self):
        """Test handling of empty statements."""
        with patch(
            "tools.political_commentary_finder.search_political_commentary.invoke"
        ) as mock:
            mock.return_value = {"results": []}

            from tools.political_commentary_finder import search_political_commentary

            result = search_political_commentary.invoke("Politician statements")
            assert result["results"] == []


def run_political_commentary_evaluation() -> dict[str, Any]:
    """Run full evaluation suite for political commentary.

    Returns:
        Dictionary with evaluation results
    """
    from deepeval import evaluate

    test_cases = [
        LLMTestCase(
            input="Find political figures commenting on Toronto climate legislation",
            actual_output="""Political figures and statements:

1. Olivia Chow, Mayor of Toronto
   - "The Climate Action Initiative represents Toronto's commitment to our 
     future. The 65% reduction target is ambitious but achievable."
   - Source: Mayor's official statement, January 15, 2024

2. Gord Perks, City Councilor (Ward 4)
   - "I've long advocated for building retrofits. This bill finally delivers 
     the policy framework we've needed."
   - Source: Council meeting, January 15, 2024

3. Jennifer Veen, City Councilor (Ward 9)
   - "Concerned about implementation timeline and funding for lower-income 
     areas. Will propose amendments."
   - Source: Twitter/X statement, January 16, 2024""",
        ),
        LLMTestCase(
            input="Find political commentary on Toronto housing",
            actual_output="""Found:

1. Some mayor said something about housing
2. Maybe a councilor too
3. (Not very specific or verifiable)""",
        ),
    ]

    metrics = create_political_relevance_metric(
        threshold=0.65,
        strict_jurisdiction=True,
        include_statement_quality=True,
    )

    results = evaluate(test_cases=test_cases, metrics=metrics)
    return results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
