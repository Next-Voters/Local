import asyncio
import logging

from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData
from utils.content.source_reliability import filter_sources

logger = logging.getLogger(__name__)


def run_legislation_finder(inputs: ChainData) -> ChainData:
    """Run the legislation finder agent for the given city."""
    city = inputs.get("region", "Unknown")

    from agents.lead_researcher_agent import invoke_legislation_finder

    topic = inputs.get("topic", "")
    agent_result = asyncio.run(invoke_legislation_finder(city, topic=topic))

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
