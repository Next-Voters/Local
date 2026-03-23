"""Legislation accuracy metric for NV Local.

Measures if discovered legislation is relevant to the target city
and represents actual municipal legislation rather than general news.
"""

from typing import Optional

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams


def legislation_accuracy_criteria() -> str:
    return """Evaluate whether the discovered legislation sources are:
    1. Relevant to the specified city/municipality
    2. Actual municipal/legislative sources (not general news)
    3. From credible government or legislative websites
    
    Score Guidelines:
    - Score 1.0: All sources are highly relevant to the city and represent actual legislation/ordinances
    - Score 0.8: Most sources are relevant, minor irrelevant sources present
    - Score 0.6: Mixed relevance, some non-municipal sources included
    - Score 0.4: Few relevant sources, mostly general news or wrong jurisdiction
    - Score 0.2: Almost all sources irrelevant to city or not actual legislation
    - Score 0.0: No relevant legislation sources found

    Consider:
    - City name mentions in legislation titles/descriptions
    - Source domains (gov, council, assembly vs. news sites)
    - Legislation-specific terms (bill, ordinance, resolution, bylaw, statute)"""


LegislationAccuracyMetric = GEval(
    name="Legislation Accuracy",
    criteria=legislation_accuracy_criteria(),
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ],
    threshold=0.7,
)


class DetailedLegislationAccuracyMetric(GEval):
    """Extended legislation accuracy metric with detailed sub-scores.

    Provides separate scores for:
    - City relevance
    - Legislative authenticity
    - Source credibility
    """

    def __init__(
        self,
        city_relevance_weight: float = 0.4,
        legislative_authenticity_weight: float = 0.3,
        source_credibility_weight: float = 0.3,
        threshold: float = 0.7,
    ):
        self.city_relevance_weight = city_relevance_weight
        self.legislative_authenticity_weight = legislative_authenticity_weight
        self.source_credibility_weight = source_credibility_weight
        super().__init__(
            name="Detailed Legislation Accuracy",
            criteria=self._build_detailed_criteria(),
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
            ],
            threshold=threshold,
        )

    def _build_detailed_criteria(self) -> str:
        return f"""Evaluate legislation sources across three dimensions:

    1. City Relevance ({int(self.city_relevance_weight * 100)}%):
       - Sources mention the target city in title/description
       - Legislation applies to the city's jurisdiction
       - Local government bodies are referenced
    
    2. Legislative Authenticity ({int(self.legislative_authenticity_weight * 100)}%):
       - Sources are from actual legislative/government bodies
       - Content represents bills, ordinances, resolutions, bylaws
       - Not general news articles about politics
    
    3. Source Credibility ({int(self.source_credibility_weight * 100)}%):
       - Official government domains (gov, .gov, council, assembly)
       - Established legal/municipal sources
       - Avoids opinion pieces or advocacy sites

    Provide an overall score 0-1 considering all three dimensions."""


def create_legislation_accuracy_metric(
    threshold: float = 0.7, detailed: bool = False, **kwargs
) -> GEval:
    """Factory function to create legislation accuracy metric.

    Args:
        threshold: Minimum passing score (default: 0.7)
        detailed: Use detailed metric with sub-scores
        **kwargs: Additional parameters for detailed metric

    Returns:
        Configured legislation accuracy metric
    """
    if detailed:
        return DetailedLegislationAccuracyMetric(threshold=threshold, **kwargs)
    return GEval(
        name="Legislation Accuracy",
        criteria=legislation_accuracy_criteria(),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        threshold=threshold,
    )
