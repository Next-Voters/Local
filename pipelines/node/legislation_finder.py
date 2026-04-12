import logging

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda

from config.constants import AGENT_RECURSION_LIMIT
from utils.schemas import ChainData
from utils.async_runner import run_async
from utils.content.source_reliability import filter_sources

logger = logging.getLogger(__name__)


async def _invoke_legislation_finder(city: str) -> dict:
    """Build and invoke the legislation finder agent."""
    from agents.legislation_finder import build_legislation_finder
    agent = await build_legislation_finder()
    return await agent.ainvoke(
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

    logger.info(
        "Legislation finder for %s: %d accepted / %d unique",
        city, len(legislation_sources), len(unique_sources),
    )
    return {**inputs, "legislation_sources": legislation_sources}


legislation_finder_chain = RunnableLambda(run_legislation_finder)
