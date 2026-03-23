"""Summary quality metric for NV Local.

Measures factual accuracy and completeness of summaries
produced by the SummaryWriter component.
"""

from typing import Optional

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams


def summary_quality_criteria() -> str:
    return """Evaluate the quality of the legislation summary across:

    1. Factual Accuracy (Critical):
       - All factual claims should be verifiable from source material
       - No hallucinated dates, numbers, or legal references
       - Correct attribution of legislation to government bodies
    
    2. Completeness:
       - All key legislation mentioned in source material is covered
       - Important details (dates, sponsors, vote counts) included
       - No significant gaps in coverage
    
    3. Clarity & Structure:
       - Clear hierarchical organization
       - Appropriate use of bullet points
       - Professional tone suitable for voter information
    
    4. Objectivity:
       - Balanced presentation of legislation
       - No editorializing or political spin
       - Facts presented neutrally

    Score Guidelines:
    - 1.0: Excellent across all dimensions
    - 0.8: Minor issues in one dimension
    - 0.6: Noticeable issues in 2+ dimensions
    - 0.4: Significant gaps in accuracy or completeness
    - 0.2: Major factual errors or missing critical information
    - 0.0: Completely inaccurate or useless summary"""


SummaryQualityMetric = GEval(
    name="Summary Quality",
    criteria=summary_quality_criteria(),
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.RETRIEVAL_CONTEXT,
    ],
    threshold=0.75,
)


class MultiDimensionalSummaryMetric(GEval):
    """Summary metric with separate dimension scores."""

    def __init__(
        self,
        factual_weight: float = 0.4,
        completeness_weight: float = 0.25,
        clarity_weight: float = 0.2,
        objectivity_weight: float = 0.15,
        threshold: float = 0.75,
    ):
        self.factual_weight = factual_weight
        self.completeness_weight = completeness_weight
        self.clarity_weight = clarity_weight
        self.objectivity_weight = objectivity_weight
        super().__init__(
            name="Multi-Dimensional Summary Quality",
            criteria=self._build_multi_dimensional_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.RETRIEVAL_CONTEXT,
            ],
            threshold=threshold,
        )

    def _build_multi_dimensional_criteria(self) -> str:
        return f"""Evaluate summary quality across four weighted dimensions:

    1. Factual Accuracy ({int(self.factual_weight * 100)}%):
       - Claims verifiable from source material
       - No hallucinated information
       - Correct legal references and citations
    
    2. Completeness ({int(self.completeness_weight * 100)}%):
       - All major legislation covered
       - Key details included (dates, sponsors, outcomes)
       - No significant coverage gaps
    
    3. Clarity & Structure ({int(self.clarity_weight * 100)}%):
       - Well-organized with clear hierarchy
       - Appropriate formatting (bullets, sections)
       - Professional, accessible language
    
    4. Objectivity ({int(self.objectivity_weight * 100)}%):
       - Neutral presentation of facts
       - No political bias or spin
       - Balanced coverage of multiple perspectives

    Provide overall weighted score 0-1."""


class SchemaComplianceMetric(GEval):
    """Metric to validate WriterOutput schema compliance."""

    def __init__(self, threshold: float = 1.0):
        super().__init__(
            name="Schema Compliance",
            criteria=self._build_schema_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            threshold=threshold,
        )

    def _build_schema_criteria(self) -> str:
        return """Validate that the output strictly follows the WriterOutput schema:

    Required fields:
    - title: string (non-empty, descriptive title of the legislation)
    - body: string (main content in bullet-point format)
    - summary: string (brief summary of the content)
    
    Quality requirements:
    - All three fields must be present
    - title should be concise but descriptive
    - body should be in bullet-point format
    - summary should be 1-3 sentences maximum
    
    Score 1.0 only if ALL requirements met.
    Score 0.5 if minor formatting issues.
    Score 0.0 if fields missing or fundamentally wrong format."""


def create_summary_quality_metric(
    threshold: float = 0.75,
    multi_dimensional: bool = False,
    include_schema_check: bool = True,
    **kwargs,
) -> list[GEval]:
    """Factory function to create summary quality metrics.

    Args:
        threshold: Minimum passing score
        multi_dimensional: Use multi-dimensional metric
        include_schema_check: Include schema compliance metric
        **kwargs: Additional parameters

    Returns:
        List of configured metrics
    """
    metrics = []

    if multi_dimensional:
        metrics.append(MultiDimensionalSummaryMetric(threshold=threshold, **kwargs))
    else:
        metrics.append(SummaryQualityMetric)

    if include_schema_check:
        metrics.append(SchemaComplianceMetric())

    return metrics
