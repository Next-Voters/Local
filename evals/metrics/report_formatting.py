"""Report formatting metric for NV Local.

Measures if markdown reports follow expected structure
and formatting conventions.
"""

from typing import Optional

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams


def report_formatting_criteria() -> str:
    return """Evaluate markdown report formatting and structure:

    1. Required Sections Present:
       - Title section (# header)
       - Summary section (## Summary)
       - Full Report section (## Full Report or similar)
       - Politician Statements section (if applicable)
    
    2. Markdown Syntax Correctness:
       - Proper header hierarchy (H1 > H2 > H3)
       - Correct bullet point syntax (- or *)
       - No broken markdown or rendering issues
       - Consistent formatting throughout
    
    3. Content Organization:
       - Logical flow from summary to details
       - Clear separation between sections
       - Easy navigation for readers
    
    4. Professional Quality:
       - Appropriate length for content
       - Readable formatting (not too dense/sparse)
       - Consistent styling choices

    Score Guidelines:
    - 1.0: Perfect structure, all sections present, clean markdown
    - 0.85: Minor formatting issues, all sections present
    - 0.7: Most sections present, some formatting problems
    - 0.5: Missing major sections, noticeable formatting issues
    - 0.25: Major structural problems
    - 0.0: Not a valid report or completely unstructured"""


ReportFormattingMetric = GEval(
    name="Report Formatting",
    criteria=report_formatting_criteria(),
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
    threshold=0.75,
)


class SectionPresenceMetric(GEval):
    """Strict metric for required section presence."""

    def __init__(
        self,
        required_sections: Optional[list[str]] = None,
        threshold: float = 1.0,
    ):
        self.required_sections = required_sections or [
            "# Title",
            "## Summary",
            "## Full Report",
            "## Politician",
        ]
        super().__init__(
            name="Section Presence",
            criteria=self._build_section_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            threshold=threshold,
        )

    def _build_section_criteria(self) -> str:
        sections_str = "\n    - ".join(self.required_sections)
        return f"""Strict evaluation of report section structure.

    Required sections to find in markdown:
    - {sections_str}

    Scoring:
    - 1.0: ALL required sections present with correct markdown headers
    - 0.8: All sections present but minor header formatting issues
    - 0.6: Missing 1 required section
    - 0.4: Missing 2 required sections
    - 0.2: Missing 3 required sections
    - 0.0: Missing all or most required sections
    
    Check specifically for:
    - # headers for main title
    - ## headers for major sections
    - Proper markdown header syntax (# not ## or ### for title)"""


class MarkdownSyntaxMetric(GEval):
    """Metric focused purely on markdown syntax correctness."""

    def __init__(self, threshold: float = 0.9):
        super().__init__(
            name="Markdown Syntax",
            criteria=self._build_syntax_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            threshold=threshold,
        )

    def _build_syntax_criteria(self) -> str:
        return """Evaluate only markdown syntax correctness:

    Valid syntax to check:
    - Headers: # through ###### with space after #
    - Bold: **text** or __text__
    - Italic: *text* or _text_
    - Lists: - or * or 1. with space after marker
    - Links: [text](url)
    - Horizontal rules: --- or *** or ___
    
    Invalid syntax:
    - Missing space after # in headers
    - Unmatched brackets
    - Broken list formatting
    - Improper nesting
    
    Score 1.0: Perfect markdown syntax throughout
    Score 0.9: 1-2 minor syntax errors
    Score 0.75: Several syntax issues that don't break rendering
    Score 0.5: Multiple syntax errors affecting readability
    Score 0.25: Extensive syntax problems
    Score 0.0: Mostly invalid markdown"""


def create_report_formatting_metric(
    threshold: float = 0.75,
    strict_sections: bool = True,
    check_syntax: bool = True,
    required_sections: Optional[list[str]] = None,
) -> list[GEval]:
    """Factory function to create report formatting metrics.

    Args:
        threshold: Minimum passing score
        strict_sections: Include strict section presence check
        check_syntax: Include markdown syntax check
        required_sections: Custom required sections

    Returns:
        List of configured metrics
    """
    metrics = [ReportFormattingMetric]

    if strict_sections:
        metrics.append(SectionPresenceMetric(required_sections=required_sections))

    if check_syntax:
        metrics.append(MarkdownSyntaxMetric())

    return metrics
