"""Content retrieval pipeline node.

Fetches raw page content for each URL discovered by the legislation finder
agent.  URLs that were already extracted inline (PDFs parsed by the web_search
tool) are passed through without re-fetching or re-compressing.
"""

import logging

import httpx
from langchain_core.runnables import RunnableLambda

from config.constants import (
    CONTENT_MAX_CHARS_PER_URL,
    CONTENT_MAX_URLS,
    CONTENT_MIN_CHARS_PER_URL,
    CONTENT_TOTAL_CHAR_BUDGET,
)
from utils.async_runner import run_async
from utils.concurrency import run_parallel
from utils.content.compressor import compress_text
from utils.tools.utils.extract import extract_url_content
from utils.schemas import ChainData

logger = logging.getLogger(__name__)


def run_content_retrieval(inputs: ChainData) -> ChainData:
    """Fetch and compress legislation page content.

    ``legislation_sources`` may contain plain URL strings *or* dicts with
    pre-fetched content (``{"url": str, "content": str, "source": "pdf"}``).
    Pre-fetched items are passed through directly; plain URLs are fetched via
    Tavily Extract with a ``markdown.new`` fallback, then compressed.
    """
    legislation_sources = inputs.get("legislation_sources", [])

    if not legislation_sources:
        return {**inputs, "legislation_content": []}

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
        return {**inputs, "legislation_content": []}

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
            url_to_content = run_async(lambda: extract_url_content(urls_to_fetch))
            logger.info(
                "Tavily Extract returned content for %d/%d URLs.",
                len(url_to_content),
                len(urls_to_fetch),
            )
        except Exception as e:
            logger.warning("Tavily Extract failed: %s", e)

        # Fallback to markdown.new for URLs Tavily didn't return.
        for url in urls_to_fetch:
            if url in url_to_content:
                continue
            try:
                response = httpx.get(
                    f"https://markdown.new/{url}",
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()
                text = response.text.strip()
                if text:
                    url_to_content[url] = text
            except (httpx.HTTPError, httpx.InvalidURL, ValueError):
                pass

    def _compress_capped(url: str) -> str:
        raw = url_to_content[url]
        if len(raw) > per_url_cap:
            raw = raw[:per_url_cap]
        return compress_text(raw)

    # Compress newly-fetched pages in parallel. BERT forward passes release
    # the GIL, so threads give real wall-clock wins over the previous
    # sequential compress_text loop. Raw text is capped at per_url_cap
    # before compression to keep the downstream LLM context bounded.
    compress_targets = [u for u in ordered_urls if u in url_to_content and u not in pre_fetched]
    compressed_by_url: dict[str, str] = {}
    if compress_targets:
        parallel_results = run_parallel(_compress_capped, compress_targets)
        for res in parallel_results:
            if res.ok and res.value is not None:
                compressed_by_url[res.item] = res.value
            else:
                logger.warning("Compression failed for %s: %r", res.item, res.error)

    # Assemble final content list in the original source order.
    legislation_content: list[str] = []
    for url in ordered_urls:
        if url in pre_fetched:
            # Already compressed by the web_search tool — pass through.
            legislation_content.append(pre_fetched[url])
        elif url in compressed_by_url:
            legislation_content.append(compressed_by_url[url])
        elif url in url_to_content:
            # Parallel compression failed; fall back to the capped raw text
            # so the downstream context stays bounded.
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

    return {**inputs, "legislation_content": legislation_content}


content_retrieval_chain = RunnableLambda(run_content_retrieval)
