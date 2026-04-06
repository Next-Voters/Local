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

    # Extract sources collected by web_search tool calls.
    # Sources are either plain URL strings or dicts {"url", "content", "source"} for
    # PDFs that were extracted inline by the web_search tool.
    all_sources = agent_result.get("legislation_sources", [])
    # Deduplicate while preserving order, keying on the URL regardless of type.
    seen: set[str] = set()
    unique_sources: list[str | dict] = []
    for source in all_sources:
        url = source["url"] if isinstance(source, dict) else source
        if url and url not in seen:
            seen.add(url)
            unique_sources.append(source)

    # Domain-level reliability filter (no API key, no external service).
    plain_urls = [s["url"] if isinstance(s, dict) else s for s in unique_sources]
    logger.info("Source reliability check for %d unique URLs:", len(plain_urls))
    accepted_urls = {scored["url"] for scored in filter_sources(plain_urls)}

    # Rebuild the source list preserving dict items (pre-fetched PDF content).
    legislation_sources = [
        s for s in unique_sources
        if (s["url"] if isinstance(s, dict) else s) in accepted_urls
    ]

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
        city, len(legislation_sources), len(unique_sources), len(legislative_events),
    )
    return {**inputs, "legislation_sources": legislation_sources, "legislative_events": legislative_events}


legislation_finder_chain = RunnableLambda(run_legislation_finder)
