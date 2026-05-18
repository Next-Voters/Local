"""Content retrieval pipeline node.

Fetches raw page content for each URL discovered by the legislation finder
agent.  URLs that were already extracted inline (PDFs parsed by the web_search
tool) are passed through without re-fetching or re-compressing.

Processes each topic's sources independently via ``topic_results``.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.runnables import RunnableLambda

from config.constants import (
    CONTENT_MAX_CHARS_PER_URL,
    CONTENT_MAX_URLS,
    CONTENT_MIN_CHARS_PER_URL,
    CONTENT_TOTAL_CHAR_BUDGET,
)
from utils.content.compressor import compress_text
from utils.logger import get_logger
from tools.services.extract import extract_url_content
from utils.schemas import ChainData

logger = get_logger(__name__)


def _retrieve_for_topic(
    legislation_sources: list[str | dict],
    compression_query: str | None,
) -> list[str]:
    """Fetch and compress content for a single topic's sources."""
    if not legislation_sources:
        return []

    # Separate pre-fetched (PDF) content from URLs that still need fetching.
    pre_fetched: dict[str, str] = {}  # url → already-compressed content
    urls_to_fetch: list[str] = []
    ordered_urls: list[str] = []  # maintains original ordering for output

    for source in legislation_sources:
        if isinstance(source, dict):
            url = source.get("url", "").strip()
            content = source.get("content", "")
            if url and content:
                pre_fetched[url] = content
                ordered_urls.append(url)
            elif url:
                urls_to_fetch.append(url)
                ordered_urls.append(url)
        elif isinstance(source, str) and source.strip():
            url = source.strip()
            urls_to_fetch.append(url)
            ordered_urls.append(url)

    if not ordered_urls:
        return []

    # Cap URLs to avoid context overflow in downstream LLM calls.
    ordered_urls = ordered_urls[:CONTENT_MAX_URLS]
    urls_to_fetch = [u for u in urls_to_fetch if u in set(ordered_urls)]

    # Adaptive per-URL char budget: spread the total budget across the URLs
    # we actually have. Small cities (few URLs) each get more context; large
    # cities compress harder. Floors/ceilings prevent degenerate splits.
    per_url_cap = CONTENT_TOTAL_CHAR_BUDGET // max(len(ordered_urls), 1)
    per_url_cap = max(CONTENT_MIN_CHARS_PER_URL, min(CONTENT_MAX_CHARS_PER_URL, per_url_cap))

    # Fetch non-PDF URLs via Tavily Extract.
    url_to_content: dict[str, str] = {}
    if urls_to_fetch:
        try:
            url_to_content = extract_url_content(urls_to_fetch)
            logger.info(
                "Tavily Extract returned content for %d/%d URLs.",
                len(url_to_content),
                len(urls_to_fetch),
            )
        except Exception as e:
            logger.warning("Tavily Extract failed: %s", e)

    def _compress_capped(url: str) -> str:
        raw = url_to_content[url]
        if len(raw) > per_url_cap:
            raw = raw[:per_url_cap]
        return compress_text(raw, query=compression_query)

    # Compress newly-fetched pages in parallel.
    compress_targets = [u for u in ordered_urls if u in url_to_content and u not in pre_fetched]
    compressed_by_url: dict[str, str] = {}
    if compress_targets:
        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(_compress_capped, url): url for url in compress_targets}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    compressed_by_url[url] = future.result()
                except Exception:
                    logger.warning("Compression failed for %s", url, exc_info=True)

    # Assemble final content list in the original source order.
    legislation_content: list[str] = []
    for url in ordered_urls:
        if url in pre_fetched:
            legislation_content.append(pre_fetched[url])
        elif url in compressed_by_url:
            legislation_content.append(compressed_by_url[url])
        elif url in url_to_content:
            raw = url_to_content[url]
            if len(raw) > per_url_cap:
                raw = raw[:per_url_cap]
            legislation_content.append(raw)
        else:
            legislation_content.append(f"[Failed to fetch: {url}]")

    successful = sum(
        1 for c in legislation_content if not c.startswith("[Failed to fetch:")
    )
    pre_fetched_count = sum(1 for u in ordered_urls if u in pre_fetched)
    logger.info(
        "Content retrieval: %d/%d URLs successful (%d pre-fetched PDFs).",
        successful,
        len(ordered_urls),
        pre_fetched_count,
    )

    return legislation_content


def run_content_retrieval(inputs: ChainData) -> ChainData:
    """Fetch and compress legislation page content for each topic."""
    topic_results = inputs.get("topic_results", {})

    for topic, result in topic_results.items():
        legislation_sources = result.get("legislation_sources", [])
        compression_query = topic.strip() or None

        logger.info("Content retrieval for topic: %s (%d sources)", topic, len(legislation_sources))
        legislation_content = _retrieve_for_topic(legislation_sources, compression_query)
        result["legislation_content"] = legislation_content

    return {**inputs, "topic_results": topic_results}


content_retrieval_chain = RunnableLambda(run_content_retrieval)
