"""Political relevance metric for NV Local.

Measures if political figures and their statements are relevant
to the target city and its legislative issues.
"""

from typing import Optional

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams


def political_relevance_criteria() -> str:
    return """Evaluate political figure and statement relevance:

    1. Geographic Relevance:
       - Politicians represent or serve the target city/jurisdiction
       - Statements relate to city-specific issues
       - Officials from relevant local government bodies
    
    2. Topic Relevance:
       - Statements address legislation being reported on
       - Comments relate to municipal/urban issues
       - Position statements on relevant policy matters
    
    3. Authority & Credibility:
       - Figures hold relevant elected/appointed positions
       - Comments come from official sources or verified accounts
       - Appropriate balance of perspectives (not just one party)
    
    4. Currency:
       - Statements are recent (within last 1-2 years)
       - Addresses current legislative session topics
       - Not outdated or historical commentary

    Score Guidelines:
    - 1.0: All figures highly relevant, statements directly address legislation
    - 0.8: Most figures relevant, statements connect to issues
    - 0.6: Mixed relevance, some figures/statements off-topic
    - 0.4: Few relevant figures, mostly generic political statements
    - 0.2: Irrelevant figures or statements not connected to city
    - 0.0: No relevant political figures or statements found"""


PoliticalRelevanceMetric = GEval(
    name="Political Relevance",
    criteria=political_relevance_criteria(),
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
    threshold=0.65,
)


class JurisdictionalRelevanceMetric(GEval):
    """Metric focused on jurisdictional correctness of political figures."""

    def __init__(self, threshold: float = 0.8):
        super().__init__(
            name="Jurisdictional Relevance",
            criteria=self._build_jurisdictional_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            threshold=threshold,
        )

    def _build_jurisdictional_criteria(self) -> str:
        return """Strictly evaluate whether political figures have proper jurisdiction:

    Correct Jurisdiction:
    - Mayor of the target city
    - City council members
    - Local assembly representatives
    - County officials for the area
    - State/provincial representatives for the district
    
    Incorrect Jurisdiction:
    - Federal officials (unless city-specific)
    - Representatives from other cities
    - International officials
    - General political commentators without local role
    
    Score 1.0: All figures have correct jurisdiction
    Score 0.8: 1-2 figures slightly off jurisdiction
    Score 0.5: Multiple figures with wrong jurisdiction
    Score 0.0: No figures with correct jurisdiction"""


class StatementQualityMetric(GEval):
    """Metric for quality of political statements themselves."""

    def __init__(self, threshold: float = 0.6):
        super().__init__(
            name="Statement Quality",
            criteria=self._build_statement_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            threshold=threshold,
        )

    def _build_statement_criteria(self) -> str:
        return """Evaluate the quality of political statements/comments:

    1. Source Quality:
       - Official statements from verified sources
       - Credible news outlets with direct quotes
       - Official social media accounts (verified)
    
    2. Content Quality:
       - Substantive commentary on legislation
       - Clear positions on issues
       - Not generic platitudes or non-responses
    
    3. Attribution:
       - Clear who said what
       - Appropriate use of direct quotes vs summaries
       - Proper source links provided
    
    4. Balance:
       - Representation of different perspectives
       - Not one-sided political coverage
       - Multiple relevant viewpoints included

    Score 1.0: Excellent across all dimensions
    Score 0.75: Minor issues in one area
    Score 0.5: Noticeable problems in 2+ areas
    Score 0.25: Significant quality issues
    Score 0.0: Useless statement collection"""


def create_political_relevance_metric(
    threshold: float = 0.65,
    strict_jurisdiction: bool = False,
    include_statement_quality: bool = True,
) -> list[GEval]:
    """Factory function to create political relevance metrics.

    Args:
        threshold: Minimum passing score
        strict_jurisdiction: Include strict jurisdictional check
        include_statement_quality: Include statement quality metric

    Returns:
        List of configured metrics
    """
    metrics = [PoliticalRelevanceMetric]

    if strict_jurisdiction:
        metrics.append(JurisdictionalRelevanceMetric())

    if include_statement_quality:
        metrics.append(StatementQualityMetric())

    return metrics
