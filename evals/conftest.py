"""Pytest configuration and fixtures for NV Local evaluation suite.

Provides mocks for external APIs (Brave Search, Wikidata, LLM calls)
to enable isolated unit testing of components.
"""

from __future__ import annotations

import json
from typing import Any, Generator
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage


@pytest.fixture
def mock_city() -> str:
    """Standard test city."""
    return "Toronto"


@pytest.fixture
def mock_city_nyc() -> str:
    """NYC test city."""
    return "New York City"


@pytest.fixture
def mock_city_san_diego() -> str:
    """San Diego test city."""
    return "San Diego"


@pytest.fixture
def sample_legislation_sources() -> list[dict[str, Any]]:
    """Sample legislation sources for Toronto."""
    return [
        {
            "url": "https://www.toronto.ca/legdocs/mmis/2024/cc/billd -it/2024-cc-doc-1.pdf",
            "organization": "Toronto City Council",
            "title": "Bill 1: Climate Action Initiative",
            "description": "Municipal climate action plan for Toronto 2024-2030",
            "date": "2024-01-15",
        },
        {
            "url": "https://www.toronto.ca/legdocs/mmis/2024/cc/billd -it/2024-cc-doc-2.pdf",
            "organization": "Toronto City Council",
            "title": "Bill 2: Affordable Housing Strategy",
            "description": "New affordable housing requirements for developments",
            "date": "2024-01-22",
        },
        {
            "url": "https://www.toronto.ca/council/transit-expansion/",
            "organization": "Toronto Transit Commission",
            "title": "Transit Expansion Plan 2024",
            "description": "Ontario Line and other transit improvements",
            "date": "2024-02-01",
        },
    ]


@pytest.fixture
def sample_legislation_sources_nyc() -> list[dict[str, Any]]:
    """Sample legislation sources for NYC."""
    return [
        {
            "url": "https://legistar.council.nyc.gov/LegislationDetail.aspx?ID=1234567",
            "organization": "NYC City Council",
            "title": "Intro 1234: Green New Deal for NYC",
            "description": "Climate sustainability legislation",
            "date": "2024-02-15",
        },
        {
            "url": "https://www.nyc.gov/housing-development",
            "organization": "NYC Department of Housing",
            "title": "Housing Preservation Plan",
            "description": "Mandatory inclusionary housing requirements",
            "date": "2024-01-30",
        },
    ]


@pytest.fixture
def sample_legislation_content() -> str:
    """Sample legislation content for summarization."""
    return """
    TORONTO CITY COUNCIL LEGISLATION SUMMARY
    
    Bill 1: Climate Action Initiative
    
    Date: January 15, 2024
    Sponsors: Mayor and 15 Council Members
    
    Key Provisions:
    - Target 65% reduction in greenhouse gas emissions by 2030
    - Mandatory building retrofits for structures over 5,000 sq ft
    - $50 million annual investment in renewable energy infrastructure
    - New electric vehicle charging requirements for all new developments
    - Enhanced tree canopy targets (40% coverage by 2050)
    
    Vote: Passed 38-7
    
    Bill 2: Affordable Housing Strategy
    
    Date: January 22, 2024
    Sponsors: Housing Committee Chair and 12 Council Members
    
    Key Provisions:
    - Require 20% affordable units in developments over 100 units
    - Income-based rent control provisions
    - $100 million housing trust fund
    - Streamlined approval process for affordable housing projects
    - Partnerships with non-profit housing providers
    
    Vote: Passed 42-3
    """


@pytest.fixture
def sample_legislation_notes() -> str:
    """Sample compressed notes from note_taker."""
    return """
    CLIMATE ACTION:
    - 65% GHG reduction target by 2030
    - Building retrofits mandatory for 5000+ sq ft
    - $50M renewable energy investment
    - EV charging in new developments
    - 40% tree canopy by 2050
    
    HOUSING:
    - 20% affordable units required (100+ unit buildings)
    - Income-based rent control
    - $100M housing trust
    - Streamlined approvals
    - Non-profit partnerships
    """


@pytest.fixture
def sample_writer_output() -> dict[str, Any]:
    """Sample WriterOutput schema."""
    return {
        "title": "Toronto City Council Legislation Update - January 2024",
        "summary": "City Council passed significant climate action and housing legislation including a 65% GHG reduction target and mandatory affordable housing requirements.",
        "body": """- **Climate Action Initiative (Bill 1)**: Passed 38-7, establishes 65% GHG reduction target by 2030, mandates building retrofits, $50M renewable energy investment

- **Affordable Housing Strategy (Bill 2)**: Passed 42-3, requires 20% affordable units in large developments, establishes $100M housing trust, implements income-based rent control

- **Transit Expansion**: TTC approved Ontario Line expansion plan with federal and provincial funding

- Key themes: Housing affordability and climate sustainability dominate 2024 legislative agenda""",
    }


@pytest.fixture
def sample_politician_data() -> list[dict[str, Any]]:
    """Sample political figure data."""
    return [
        {
            "name": "Olivia Chow",
            "position": "Mayor",
            "party": None,
            "jurisdiction": "Toronto",
            "source_url": "https://www.toronto.ca/mayor/",
        },
        {
            "name": "Josh Matlow",
            "position": "City Councilor",
            "party": "Independent",
            "jurisdiction": "Toronto - Ward 12",
            "source_url": "https://www.toronto.ca/council/josh-matlow/",
        },
        {
            "name": "Gord Perks",
            "position": "City Councilor",
            "party": "New Democrat",
            "jurisdiction": "Toronto - Ward 4",
            "source_url": None,
        },
    ]


@pytest.fixture
def sample_political_statements() -> list[dict[str, Any]]:
    """Sample political statements."""
    return [
        {
            "name": "Olivia Chow",
            "statement_summaries": [
                {
                    "source": "https://www.toronto.ca/mayor/news/",
                    "summary": "Mayor Chow emphasized the climate legislation as a historic step, stating it represents Toronto's commitment to being a leader in municipal climate action.",
                },
                {
                    "source": "https://twitter.com/OliviaChow",
                    "summary": "On social media, the Mayor highlighted the housing strategy as addressing the core crisis facing Toronto families.",
                },
            ],
        },
        {
            "name": "Josh Matlow",
            "statement_summaries": [
                {
                    "source": "https://www.thestar.com/opinion/st -it-by-josh-matlow",
                    "summary": "Councilor Matlow expressed conditional support for climate bill, noting need for more funding for retrofits in lower-income areas.",
                },
            ],
        },
    ]


@pytest.fixture
def sample_markdown_report() -> str:
    """Sample markdown report output."""
    return """# Toronto City Council Legislation Update - January 2024

## Summary

City Council passed significant climate action and housing legislation including a 65% GHG reduction target and mandatory affordable housing requirements.

## Full Report

- **Climate Action Initiative (Bill 1)**: Passed 38-7, establishes 65% GHG reduction target by 2030, mandates building retrofits, $50M renewable energy investment

- **Affordable Housing Strategy (Bill 2)**: Passed 42-3, requires 20% affordable units in large developments, establishes $100M housing trust, implements income-based rent control

- **Transit Expansion**: TTC approved Ontario Line expansion plan with federal and provincial funding

- Key themes: Housing affordability and climate sustainability dominate 2024 legislative agenda

---

## Politician Public Statements
### Coming Soon!

### Olivia Chow

**Legislation Source Link:** https://www.toronto.ca/mayor/news/

Mayor Chow emphasized the climate legislation as a historic step, stating it represents Toronto's commitment to being a leader in municipal climate action.

**Legislation Source Link:** https://twitter.com/OliviaChow

On social media, the Mayor highlighted the housing strategy as addressing the core crisis facing Toronto families.

### Josh Matlow

**Legislation Source Link:** https://www.thestar.com/opinion/st -it-by-josh-matlow

Councilor Matlow expressed conditional support for climate bill, noting need for more funding for retrofits in lower-income areas.
"""


@pytest.fixture
def mock_brave_search() -> MagicMock:
    """Mock Brave Search API responses."""
    mock = MagicMock()
    mock.return_value = {
        "web": {
            "results": [
                {
                    "title": "Toronto City Council Meeting - January 2024",
                    "url": "https://www.toronto.ca/legdocs/mmis/2024/cc/billd -it/2024-cc-doc-1.pdf",
                    "description": "Official city council legislation documents",
                },
                {
                    "title": "Toronto Municipal Code - Active Legislation",
                    "url": "https://www.toronto.ca/legdocs/mmis/2024/",
                    "description": "Current municipal legislation and bylaws",
                },
            ]
        }
    }
    return mock


@pytest.fixture
def mock_wikidata() -> MagicMock:
    """Mock Wikidata API responses."""
    mock = MagicMock()
    mock.return_value = {
        "results": [
            {
                "name": "Olivia Chow",
                "position": "Mayor of Toronto",
                "jurisdiction": "Toronto",
                "type": "human",
            },
            {
                "name": "Toronto City Council",
                "position": "Legislative body",
                "jurisdiction": "Toronto",
                "type": "government organization",
            },
        ]
    }
    return mock


@pytest.fixture
def mock_llm_response() -> MagicMock:
    """Mock LLM response."""
    mock = MagicMock()
    mock.content = "This is a mock LLM response for testing purposes."
    return mock


@pytest.fixture
def mock_structured_llm_response() -> dict[str, Any]:
    """Mock structured LLM response (WriterOutput)."""
    return {
        "title": "Toronto City Council Legislation Update",
        "summary": "Summary of recent legislation.",
        "body": "Bullet points of legislation details.",
    }


@pytest.fixture
def mock_agent_state() -> dict[str, Any]:
    """Mock agent state for testing."""
    return {
        "messages": [
            HumanMessage(content="Find recent legislation for Toronto"),
            AIMessage(
                content="I found the following legislation...",
                tool_calls=[
                    {
                        "name": "web_search",
                        "args": {"query": "Toronto city council legislation 2024"},
                        "id": "call_123",
                    }
                ],
            ),
        ],
        "reflection_list": [],
        "city": "Toronto",
        "raw_legislation_sources": [],
        "reliable_legislation_sources": [],
    }


@pytest.fixture
def mock_chain_data() -> dict[str, Any]:
    """Mock chain data for pipeline testing."""
    return {
        "city": "Toronto",
        "legislation_sources": "Sample legislation sources",
        "notes": sample_legislation_notes(),
        "legislation_summary": None,
        "markdown_report": "",
    }


@pytest.fixture
def mock_retrieval_context() -> str:
    """Mock retrieval context for evaluation."""
    return """
    Source: Toronto City Council Official Website
    
    BILL 1-2024: CLIMATE ACTION INITIATIVE
    
    Passed: January 15, 2024
    Vote: 38-7
    
    AN ACT TO REDUCE GREENHOUSE GAS EMISSIONS
    
    The City of Toronto hereby establishes the following targets:
    - 65% reduction in GHG emissions by 2030
    - 100% renewable energy for city operations by 2040
    
    Requirements:
    1. All buildings over 5,000 sq ft must undergo energy audits
    2. New developments must include EV charging infrastructure
    3. $50 million annual investment in renewable energy projects
    
    BILL 2-2024: AFFORDABLE HOUSING STRATEGY
    
    Passed: January 22, 2024
    Vote: 42-3
    
    AN ACT TO ADDRESS HOUSING AFFORDABILITY
    
    The City of Toronto establishes:
    - 20% affordable housing requirement for 100+ unit developments
    - $100 million Housing Opportunities Reserve Fund
    - Income-based rent stabilization guidelines
    """


class MockBraveSearchTool:
    """Mock Brave Search tool for testing."""

    def __init__(self, results: Optional[list[dict]] = None):
        self.results = results or [
            {
                "title": "Test Legislation",
                "url": "https://example.gov/legislation",
                "description": "Test description",
            }
        ]

    def invoke(self, query: str) -> dict:
        return {"web": {"results": self.results}}


class MockWikidataTool:
    """Mock Wikidata tool for testing."""

    def __init__(self, entities: Optional[list[dict]] = None):
        self.entities = entities or [
            {"name": "Test Politician", "jurisdiction": "Test City"}
        ]

    def invoke(self, query: str) -> dict:
        return {"results": self.entities}


@pytest.fixture
def patch_brave_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch Brave Search API for all tests."""

    def mock_search(query: str, **kwargs) -> dict:
        return {
            "web": {
                "results": [
                    {
                        "title": f"Legislation related to {query}",
                        "url": f"https://example.gov/search?q={query}",
                        "description": "Mock search result",
                    }
                ]
            }
        }

    monkeypatch.setattr("agents.legislation_finder.web_search.invoke", mock_search)


@pytest.fixture
def patch_wikidata(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch Wikidata API for all tests."""

    def mock_find(query: str) -> dict:
        return {
            "results": [
                {
                    "name": query,
                    "jurisdiction": "Test City",
                    "position": "Test Position",
                }
            ]
        }

    monkeypatch.setattr(
        "agents.political_commentry_finder.political_figure_finder.invoke",
        mock_find,
    )


from typing import Optional
