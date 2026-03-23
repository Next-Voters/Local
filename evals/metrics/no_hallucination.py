"""No hallucination metric for NV Local.

Measures if outputs are grounded in source material
and don't contain hallucinated information.
"""

from typing import Optional

from deepeval.metrics import GEval, BaseMetric
from deepeval.test_case import LLMTestCaseParams


def no_hallucination_criteria() -> str:
    return """Evaluate whether the output is grounded in the provided source material:

    1. Factual Grounding:
       - All factual claims traceable to source material
       - No invented statistics, dates, or numbers
       - Proper attribution of quotes and data
    
    2. Source Attribution:
       - Clear when information comes from sources
       - No claiming unverified information as fact
       - Appropriate hedging for interpretations
    
    3. No Fabrication:
       - No invented legislation names or numbers
       - No fake quotes from officials
       - No invented outcomes or votes
    
    4. Contextual Accuracy:
       - Correct context from source material
       - No out-of-context quotes or data
       - Proper handling of ambiguous information

    Score Guidelines:
    - 1.0: Perfectly grounded, every claim supported by sources
    - 0.9: Minor overgeneralizations, 1-2 unsupported minor claims
    - 0.75: Some unsupported claims but generally grounded
    - 0.5: Noticeable fabrication or unsupported major claims
    - 0.25: Significant hallucinated content
    - 0.0: Mostly or completely hallucinated content"""


NoHallucinationMetric = GEval(
    name="No Hallucination",
    criteria=no_hallucination_criteria(),
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.RETRIEVAL_CONTEXT,
    ],
    threshold=0.85,
)


class CitationAccuracyMetric(GEval):
    """Metric specifically for citation accuracy."""

    def __init__(self, threshold: float = 0.9):
        super().__init__(
            name="Citation Accuracy",
            criteria=self._build_citation_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.RETRIEVAL_CONTEXT,
            ],
            threshold=threshold,
        )

    def _build_citation_criteria(self) -> str:
        return """Evaluate accuracy of citations and references:

    Check for:
    - URLs provided actually exist and are accessible
    - Document titles match actual documents
    - Dates cited are correct
    - Official names are accurate
    
    Common hallucinations to detect:
    - Fake URLs or malformed links
    - Wrong document titles
    - Incorrect dates
    - Misattributed quotes
    
    Score 1.0: All citations accurate and verifiable
    Score 0.8: Minor citation inaccuracies
    Score 0.6: Some incorrect citations
    Score 0.4: Many incorrect or fabricated citations
    Score 0.0: Mostly fabricated citations"""


class ClaimVerifiabilityMetric(GEval):
    """Metric for checking if claims can be verified from context."""

    def __init__(
        self,
        verifiable_weight: float = 0.6,
        contextual_weight: float = 0.4,
        threshold: float = 0.8,
    ):
        self.verifiable_weight = verifiable_weight
        self.contextual_weight = contextual_weight
        super().__init__(
            name="Claim Verifiability",
            criteria=self._build_verifiability_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.RETRIEVAL_CONTEXT,
            ],
            threshold=threshold,
        )

    def _build_verifiability_criteria(self) -> str:
        return f"""Evaluate whether output claims are verifiable from source context:

    1. Direct Verifiability ({int(self.verifiable_weight * 100)}%):
       - Claims can be directly confirmed from source material
       - Numbers, dates, names match sources exactly
       - Statistics are accurate reproductions
    
    2. Contextual Accuracy ({int(self.contextual_weight * 100)}%):
       - Claims maintain proper context from sources
       - No out-of-context distortions
       - Interpretations align with source meaning
    
    Score 1.0: All claims verifiable and properly contextualized
    Score 0.75: Most claims verifiable, minor context issues
    Score 0.5: Several unverifiable claims or context errors
    Score 0.25: Many unverifiable claims
    Score 0.0: Most or all claims cannot be verified"""


class HallucinationTypeMetric(GEval):
    """Detailed metric categorizing types of hallucinations."""

    def __init__(self, threshold: float = 0.8):
        super().__init__(
            name="Hallucination Type Analysis",
            criteria=self._build_hallucination_type_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.RETRIEVAL_CONTEXT,
            ],
            threshold=threshold,
        )

    def _build_hallucination_type_criteria(self) -> str:
        return """Identify and score specific hallucination types:

    Severe Hallucinations (Major deductions):
    - Fabricated legislation names or numbers
    - Invented official quotes
    - Fake voting records or outcomes
    - Non-existent documents or URLs
    
    Moderate Hallucinations:
    - Slightly incorrect dates or numbers
    - Misattributed statements
    - Slightly wrong official names
    - Inaccurate descriptions of legislation
    
    Minor Hallucinations:
    - Word substitutions that change meaning slightly
    - Minor context errors
    - Overgeneralizations from specific facts
    
    Scoring:
    - 1.0: No hallucinations detected
    - 0.8: Only minor hallucinations
    - 0.6: 1-2 moderate hallucinations
    - 0.4: Several moderate hallucinations
    - 0.2: Any severe hallucinations present
    - 0.0: Multiple severe hallucinations"""


def create_no_hallucination_metric(
    threshold: float = 0.85,
    include_citation_check: bool = True,
    include_verifiability: bool = True,
    detailed_analysis: bool = False,
) -> list[GEval]:
    """Factory function to create no-hallucination metrics.

    Args:
        threshold: Minimum passing score
        include_citation_check: Include citation accuracy metric
        include_verifiability: Include claim verifiability metric
        detailed_analysis: Include hallucination type analysis

    Returns:
        List of configured metrics
    """
    metrics = [NoHallucinationMetric]

    if include_citation_check:
        metrics.append(CitationAccuracyMetric())

    if include_verifiability:
        metrics.append(ClaimVerifiabilityMetric())

    if detailed_analysis:
        metrics.append(HallucinationTypeMetric())

    return metrics
