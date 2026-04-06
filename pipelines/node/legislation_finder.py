import logging
from contextlib import AsyncExitStack

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda

from config.constants import AGENT_RECURSION_LIMIT
from utils.schemas import ChainData
from utils.async_runner import run_async
from utils.mcp import registry as mcp
from utils.source_reliability import filter_sources

logger = logging.getLogger(__name__)


async def _invoke_legislation_finder(city: str) -> dict:
    """Invoke the legislation finder agent with an initial task message."""
    from agents.legislation_finder import legislation_finder_agent
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp.session("tavily"))
        if mcp.is_configured("google_calendar"):
            await stack.enter_async_context(mcp.session("google_calendar"))
        return await legislation_finder_agent.ainvoke(
            {
                "city": city,
                "messages": [
                    HumanMessage(content=f"Find recent legislation for {city}.")
                ],
            },
            config={"recursion_limit": AGENT_RECURSION_LIMIT},
        )


def run_legislation_finder(inputs: ChainData) -> ChainData:
    city = inputs.get("city", "Unknown")
    agent_result = run_async(lambda: _invoke_legislation_finder(city))

    # Extract URLs from sources collected by web_search tool calls.
    all_urls = agent_result.get("legislation_sources", [])
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)

    # Domain-level reliability filter (no API key, no external service).
    logger.info("Source reliability check for %d unique URLs:", len(unique_urls))
    accepted = filter_sources(unique_urls)
    legislation_sources = [s["url"] for s in accepted]

    # Extract and deduplicate legislative events by (title, start_date).
    raw_events = agent_result.get("legislative_events", [])
    seen_events: set[tuple[str, str]] = set()
    legislative_events = []
    for ev in raw_events:
        key = (ev.title, ev.start_date)
        if key not in seen_events:
            seen_events.add(key)
            legislative_events.append(ev)

    logger.info(
        "Legislation finder for %s: %d accepted / %d unique, %d events",
        city, len(legislation_sources), len(unique_urls), len(legislative_events),
    )
    return {**inputs, "legislation_sources": legislation_sources, "legislative_events": legislative_events}


legislation_finder_chain = RunnableLambda(run_legislation_finder)
