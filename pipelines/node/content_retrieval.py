import logging

import httpx
from langchain_core.runnables import RunnableLambda

from utils.async_runner import run_async
from utils.mcp.tavily import extract_url_content
from utils.schemas import ChainData

logger = logging.getLogger(__name__)


def run_content_retrieval(inputs: ChainData) -> ChainData:
    legislation_sources = inputs.get("legislation_sources", [])

    if not legislation_sources:
        return {**inputs, "legislation_content": []}

    urls = []
    for source in legislation_sources:
        url = source.get("url") if isinstance(source, dict) else source
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())

    if not urls:
        return {**inputs, "legislation_content": []}

    url_to_content: dict[str, str] = {}
    try:
        url_to_content = run_async(lambda: extract_url_content(urls))
        logger.info("Tavily Extract returned content for %d/%d URLs.", len(url_to_content), len(urls))
    except Exception as e:
        logger.warning("Tavily Extract failed: %s", e)

    # Fallback to markdown.new for URLs Tavily didn't return
    for url in urls:
        if url in url_to_content:
            continue
        try:
            response = httpx.get(f"https://markdown.new/{url}", timeout=30, follow_redirects=True)
            response.raise_for_status()
            text = response.text.strip()
            if text:
                url_to_content[url] = text
        except (httpx.HTTPError, httpx.InvalidURL, ValueError):
            pass

    legislation_content = []
    for url in urls:
        content = url_to_content.get(url)
        if content:
            legislation_content.append(content)
        else:
            legislation_content.append(f"[Failed to fetch: {url}]")

    successful = sum(1 for c in legislation_content if not c.startswith("[Failed to fetch:"))
    logger.info("Content retrieval: %d/%d URLs successful.", successful, len(urls))

    return {**inputs, "legislation_content": legislation_content}


content_retrieval_chain = RunnableLambda(run_content_retrieval)
