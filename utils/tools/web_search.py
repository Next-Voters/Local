"""Web search tool adapter for legislation discovery.

Thin adapter that calls the Tavily MCP server and wraps results
in LangGraph Commands for state updates.  PDF URLs are detected
deterministically and their content is extracted inline via
pymupdf4llm so it is available immediately in pipeline state.
"""

import logging
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from utils.context_compressor import compress_text
from utils.mcp.tavily import search_legislation, extract_search_results
from utils.pdf_extractor import is_pdf_url, download_and_parse_pdf

logger = logging.getLogger(__name__)


@tool
async def web_search(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("city")],
    max_results: int = 5,
) -> Command:
    """Search the web for legislation related to a specific municipality or topic.

    Uses Tavily search with a legislation profile to prioritize official government
    sites, legislative databases, and authoritative news sources.

    PDF results are detected automatically (via Content-Type / URL suffix) and
    their content is extracted and compressed inline so downstream nodes do not
    need to re-fetch them.

    Args:
        query: The search query — e.g. "Austin city council bylaws March 2026" or
               "municipal ordinance zoning city council passed".
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        city: The city to find legislation for (injected from state).
        max_results: Maximum number of results to return (default 5).

    Returns:
        A Command object that updates the state with search results.
    """
    try:
        raw_results = await search_legislation(
            query=query,
            city=city,
            max_results=max_results,
        )

        results = extract_search_results(raw_results)

        legislation_sources: list[str | dict] = []
        pdf_count = 0

        for result in results:
            url = result.get("url", "")
            if not url:
                continue

            # --- PDF detection & inline extraction ---
            if is_pdf_url(url):
                content = download_and_parse_pdf(url)
                if content:
                    compressed = compress_text(content)
                    legislation_sources.append({
                        "url": url,
                        "content": compressed,
                        "source": "pdf",
                    })
                    pdf_count += 1
                    logger.info("PDF extracted inline: %s", url)
                    continue
                # If PDF extraction failed, fall through to plain URL.

            legislation_sources.append(url)

        # Build a human-readable summary for the agent's message history.
        summary_lines = []
        for source in legislation_sources:
            if isinstance(source, dict):
                summary_lines.append(f"  - {source['url']} [PDF content extracted]")
            else:
                summary_lines.append(f"  - {source}")

        summary = (
            f"Web search for '{query}' (city: {city}) returned "
            f"{len(legislation_sources)} result(s)"
            f" ({pdf_count} PDF(s) extracted inline):\n"
            + "\n".join(summary_lines)
        )

        return Command(
            update={
                "legislation_sources": legislation_sources,
                "messages": [
                    ToolMessage(
                        content=summary,
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except ValueError as e:
        error_msg = f"Tavily API key not configured: {e}"
        return Command(
            update={
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )
    except Exception as e:
        error_msg = f"Web search failed: {e}"
        return Command(
            update={
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )
