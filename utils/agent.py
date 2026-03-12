from langgraph.prebuilt import create_react_agent
from utils.tools import legislation_finder_tools, agent_2_tools


def legislation_finder(llm):
    """Agent 1: Legislation Finder — discovers legislation URLs and bill metadata."""
    return create_react_agent(
        model=llm,
        tools=legislation_finder_tools,
        name="legislation_finder",
        prompt="You are a legislation finder agent. Your job is to search for recent legislation, fetch relevant URLs, and parse HTML to extract bill metadata. Return the URLs and metadata you find.",
    )


def build_agent_2(llm):
    """Agent 2: Scraper Builder — generates and runs scraping code, filters by date."""
    return create_react_agent(
        model=llm,
        tools=agent_2_tools,
        name="scraper_builder",
        prompt="You are a scraper builder agent. You receive legislation URLs and metadata from the previous agent. Your job is to generate Python scraping code, execute it, and filter results to the last 7 days. Return the raw legislation text and vote records.",
    )
