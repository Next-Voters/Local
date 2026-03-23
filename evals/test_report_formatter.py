"""Unit tests for ReportFormatter component.

Tests the formatter's ability to create well-structured
markdown reports from summaries and political statements.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from deepeval.test_case import LLMTestCase

from evals.metrics.report_formatting import (
    ReportFormattingMetric,
    SectionPresenceMetric,
    MarkdownSyntaxMetric,
    create_report_formatting_metric,
)
from utils.schemas import ChainData, WriterOutput


class TestReportFormatter:
    """Test suite for ReportFormatter component."""

    @pytest.fixture(autouse=True)
    def setup(
        self,
        sample_writer_output: dict[str, Any],
        sample_political_statements: list[dict],
    ):
        self.summary = sample_writer_output
        self.statements = sample_political_statements

    def test_formatter_initialization(self):
        """Test that formatter can be imported."""
        from pipelines.node.report_formatter import report_formatter_chain

        assert report_formatter_chain is not None

    def test_report_formatter_with_valid_input(
        self,
        sample_writer_output: dict[str, Any],
        sample_political_statements: list[dict],
    ):
        """Test report formatter with valid inputs."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title=sample_writer_output["title"],
                summary=sample_writer_output["summary"],
                body=sample_writer_output["body"],
            ),
            "politician_public_statements": sample_political_statements,
        }

        result = report_formatter(inputs)

        assert "markdown_report" in result
        assert isinstance(result["markdown_report"], str)
        assert len(result["markdown_report"]) > 0

    def test_report_formatter_without_summary(self):
        """Test report formatter handles missing summary gracefully."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": None,
            "politician_public_statements": [],
        }

        result = report_formatter(inputs)

        assert "markdown_report" in result
        assert "No Legislation Found" in result["markdown_report"]

    def test_report_formatter_without_politicians(
        self, sample_writer_output: dict[str, Any]
    ):
        """Test report formatter handles missing political statements."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title=sample_writer_output["title"],
                summary=sample_writer_output["summary"],
                body=sample_writer_output["body"],
            ),
            "politician_public_statements": [],
        }

        result = report_formatter(inputs)

        assert "markdown_report" in result
        assert "# " in result["markdown_report"]

    def test_report_includes_required_sections(
        self, sample_writer_output: dict[str, Any]
    ):
        """Test that report includes all required sections."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title="Test Title",
                summary="Test summary",
                body="Test body content",
            ),
            "politician_public_statements": [
                {
                    "name": "Test Politician",
                    "statement_summaries": [
                        {"source": "https://example.com", "summary": "Test statement"}
                    ],
                }
            ],
        }

        result = report_formatter(inputs)
        report = result["markdown_report"]

        assert "# Test Title" in report
        assert "## Summary" in report
        assert "## Full Report" in report
        assert "## Politician" in report
        assert "### Test Politician" in report


class TestReportFormattingMetric:
    """Test suite for report formatting evaluation metric."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.metric = ReportFormattingMetric

    def test_well_formatted_report(self):
        """Test metric scores high for well-formatted report."""
        test_case = LLMTestCase(
            input="Generate report for Toronto legislation",
            actual_output="""# Toronto City Council Legislation Update

## Summary
City Council passed major climate and housing legislation in January 2024.

## Full Report
- **Bill 1-2024**: Climate Action Initiative
- **Bill 2-2024**: Affordable Housing Strategy

---

## Politician Public Statements
### Coming Soon!

### Mayor Olivia Chow
**Source:** https://example.com/statement

Statement about the legislation here.""",
        )

        self.metric.measure(test_case)
        assert self.metric.score >= 0.75

    def test_poorly_formatted_report(self):
        """Test metric detects poorly formatted reports."""
        test_case = LLMTestCase(
            input="Generate report",
            actual_output="""Some random text that isn't really a report
No headers or structure here
Just some bullet points
- Point 1
- Point 2""",
        )

        self.metric.measure(test_case)
        assert self.metric.score < 0.5

    def test_missing_sections(self):
        """Test metric detects missing required sections."""
        test_case = LLMTestCase(
            input="Generate report",
            actual_output="""# Title

Just some content without proper section headers.""",
        )

        self.metric.measure(test_case)
        assert self.metric.score < 0.8


class TestSectionPresenceMetric:
    """Test suite for required section presence validation."""

    def test_all_sections_present(self):
        """Test detection of all required sections."""
        metric = SectionPresenceMetric(
            required_sections=[
                "# Title",
                "## Summary",
                "## Full Report",
                "## Politician",
            ]
        )

        test_case = LLMTestCase(
            input="Generate report",
            actual_output="""# Toronto Legislation

## Summary
Summary content here.

## Full Report
Report content here.

## Politician Statements
Politician content here.""",
        )

        metric.measure(test_case)
        assert metric.score >= 1.0

    def test_missing_sections(self):
        """Test detection of missing sections."""
        metric = SectionPresenceMetric(
            required_sections=["# Title", "## Summary", "## Full Report"]
        )

        test_case = LLMTestCase(
            input="Generate report",
            actual_output="""# Title

## Summary
Summary here.

Missing Full Report section.""",
        )

        metric.measure(test_case)
        assert metric.score < 1.0

    def test_custom_required_sections(self):
        """Test custom required sections."""
        metric = SectionPresenceMetric(
            required_sections=[
                "# Executive Summary",
                "## Legislation",
                "## Politicians",
            ]
        )

        test_case = LLMTestCase(
            input="Generate report",
            actual_output="""# Executive Summary
Content

## Legislation
Content

## Politicians
Content""",
        )

        metric.measure(test_case)
        assert metric.score >= 1.0


class TestMarkdownSyntaxMetric:
    """Test suite for markdown syntax validation."""

    def test_valid_markdown_syntax(self):
        """Test detection of valid markdown syntax."""
        metric = MarkdownSyntaxMetric(threshold=0.9)

        test_case = LLMTestCase(
            input="Generate report",
            actual_output="""# Title

## Section 1

- Bullet point 1
- Bullet point 2

**Bold text** and *italic text*

[Link text](https://example.com)

---

### Subsection

1. Numbered item 1
2. Numbered item 2""",
        )

        metric.measure(test_case)
        assert metric.score >= 0.9

    def test_broken_markdown_syntax(self):
        """Test detection of broken markdown."""
        metric = MarkdownSyntaxMetric(threshold=0.9)

        test_case = LLMTestCase(
            input="Generate report",
            actual_output="""#Title (missing space)

##Section (missing space)

-Bullet (missing space)
*[text(no closing bracket)""",
        )

        metric.measure(test_case)
        assert metric.score < 0.5


class TestReportFormatterIntegration:
    """Integration tests for report formatter."""

    def test_full_report_generation(
        self,
        sample_writer_output: dict[str, Any],
        sample_political_statements: list[dict],
    ):
        """Test complete report generation workflow."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title=sample_writer_output["title"],
                summary=sample_writer_output["summary"],
                body=sample_writer_output["body"],
            ),
            "politician_public_statements": sample_political_statements,
        }

        result = report_formatter(inputs)
        report = result["markdown_report"]

        assert isinstance(report, str)
        assert len(report) > 100
        assert report.startswith("#")

    def test_report_with_multiple_politicians(
        self, sample_writer_output: dict[str, Any]
    ):
        """Test report with multiple politician entries."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title="Test",
                summary="Summary",
                body="Body",
            ),
            "politician_public_statements": [
                {
                    "name": "Politician 1",
                    "statement_summaries": [
                        {"source": "https://a.com", "summary": "Statement 1"}
                    ],
                },
                {
                    "name": "Politician 2",
                    "statement_summaries": [
                        {"source": "https://b.com", "summary": "Statement 2"}
                    ],
                },
                {
                    "name": "Politician 3",
                    "statement_summaries": [
                        {"source": "https://c.com", "summary": "Statement 3"}
                    ],
                },
            ],
        }

        result = report_formatter(inputs)
        report = result["markdown_report"]

        assert "### Politician 1" in report
        assert "### Politician 2" in report
        assert "### Politician 3" in report

    def test_report_with_multiple_statements(
        self, sample_writer_output: dict[str, Any]
    ):
        """Test report with multiple statements per politician."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title="Test",
                summary="Summary",
                body="Body",
            ),
            "politician_public_statements": [
                {
                    "name": "Test Politician",
                    "statement_summaries": [
                        {"source": "https://source1.com", "summary": "First statement"},
                        {
                            "source": "https://source2.com",
                            "summary": "Second statement",
                        },
                        {"source": "https://source3.com", "summary": "Third statement"},
                    ],
                }
            ],
        }

        result = report_formatter(inputs)
        report = result["markdown_report"]

        assert report.count("source1.com") == 1
        assert report.count("source2.com") == 1
        assert report.count("source3.com") == 1


class TestReportFormatterEdgeCases:
    """Edge case tests for report formatter."""

    def test_empty_title(self):
        """Test handling of empty title."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title="",
                summary="Summary",
                body="Body",
            ),
            "politician_public_statements": [],
        }

        result = report_formatter(inputs)
        assert "markdown_report" in result

    def test_very_long_content(self):
        """Test handling of very long content."""
        from pipelines.node.report_formatter import report_formatter

        long_body = "x" * 10000

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title="Long Report",
                summary="A very long summary " * 100,
                body=long_body,
            ),
            "politician_public_statements": [],
        }

        result = report_formatter(inputs)
        assert len(result["markdown_report"]) > 10000

    def test_special_characters_in_title(self):
        """Test handling of special characters in titles."""
        from pipelines.node.report_formatter import report_formatter

        inputs: ChainData = {
            "legislation_summary": WriterOutput(
                title="Test: Special Chars & More (#1)",
                summary="Summary with émojis 🎉",
                body="- Point with **bold** and *italic*",
            ),
            "politician_public_statements": [],
        }

        result = report_formatter(inputs)
        assert "# Test:" in result["markdown_report"]


def run_report_formatter_evaluation() -> dict[str, Any]:
    """Run full evaluation suite for report formatter.

    Returns:
        Dictionary with evaluation results
    """
    from deepeval import evaluate

    test_cases = [
        LLMTestCase(
            input="Generate markdown report for Toronto legislation",
            actual_output="""# Toronto City Council Legislation Update - January 2024

## Summary
City Council passed significant climate action and housing legislation including a 65% GHG reduction target and mandatory affordable housing requirements.

## Full Report
- **Climate Action Initiative (Bill 1)**: Passed 38-7, establishes 65% GHG reduction target by 2030, mandates building retrofits, $50M renewable energy investment

- **Affordable Housing Strategy (Bill 2)**: Passed 42-3, requires 20% affordable units in large developments, establishes $100M housing trust, implements income-based rent control

---

## Politician Public Statements
### Coming Soon!

### Olivia Chow
**Legislation Source Link:** https://www.toronto.ca/mayor/news/

Mayor Chow emphasized the climate legislation as a historic step.

### Josh Matlow
**Legislation Source Link:** https://www.thestar.com/opinion/

Councilor Matlow expressed conditional support for the climate bill.""",
        ),
        LLMTestCase(
            input="Generate report",
            actual_output="""Random text without proper structure
No headers or formatting
Just plain text""",
        ),
    ]

    metrics = create_report_formatting_metric(
        threshold=0.75,
        strict_sections=True,
        check_syntax=True,
    )

    results = evaluate(test_cases=test_cases, metrics=metrics)
    return results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
