"""Content retrieval pipeline node.

Fetches raw page content for each URL discovered by the legislation finder
agent.  URLs that were already extracted inline (PDFs parsed by the web_search
tool) are passed through without re-fetching or re-compressing.
"""

import logging

import httpx
from langchain_core.runnables import RunnableLambda

from utils.async_runner import run_async
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
    # 20 content-rich pages (e.g. NYC) can exceed the 272K-token input limit
    # even after LLMLingua-2 compression; 10 sources is ample for research quality.
    ordered_urls = ordered_urls[:10]
    urls_to_fetch = [u for u in urls_to_fetch if u in set(ordered_urls)]

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

    # Assemble final content list in the original source order.
    legislation_content: list[str] = []
    for url in ordered_urls:
        if url in pre_fetched:
            # Already compressed by the web_search tool — pass through.
            legislation_content.append(pre_fetched[url])
        elif url in url_to_content:
            legislation_content.append(compress_text(url_to_content[url]))
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
