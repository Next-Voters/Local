"""Political commentary agent for NV Local.

This module defines the political_commentary_agent that finds political figures
and their commentary for a given city. It uses the BaseReActAgent template
with political figure finder, commentary search, and social media tools.

The agent helps voters identify relevant political figures and their publicly
available commentary on local issues. When more context is needed to be fair
and holistic, it can also search their official social media accounts.

Tools are thin adapters that call MCP servers and wrap results in LangGraph Commands.
"""

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from agents.base_agent_template import BaseReActAgent
from utils.mcp.political_figures import (
    find_political_figures as mcp_find_figures,
    extract_commentary as mcp_extract_commentary,
    search_politician_tweets as mcp_search_tweets,
)
from utils.mcp.tavily import search_political_content, extract_search_results
from config.system_prompts import political_commentary_sys_prompt
from utils.schemas import PoliticalCommentaryState


# ---------------------------------------------------------------------------
# Tool adapters (MCP call → LangGraph Command)
# ---------------------------------------------------------------------------


@tool
async def political_figure_finder(
    tool_call_id: Annotated[str, InjectedToolCallId],
    city: Annotated[str, InjectedState("city")],
) -> Command:
    """Find political figures (candidates, elected officials) for a specific city.

    Queries an external data service to find Canadian and American political
    candidates and elected officials for the given city. The country is
    automatically detected using geocoding.

    Args:
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        city: The city name to search for political figures (injected from state).

    Returns:
        A Command object that updates the state with political figure data.
    """
    try:
        result = await mcp_find_figures(city=city)

        if result.get("error"):
            return Command(
                update={
                    "political_figures": [],
                    "messages": [
                        ToolMessage(
                            content=result["error"],
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        figures = result.get("figures", [])
        country = result.get("country", "")

        summary_lines = [
            f"Found {len(figures)} political figure(s) in {city}, {country}:"
        ]
        for pf in figures:
            summary_lines.append(
                f"  - {pf['name']} ({pf.get('position', 'Unknown position')})"
            )

        return Command(
            update={
                "political_figures": figures,
                "country": country,
                "messages": [
                    ToolMessage(
                        content="\n".join(summary_lines),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        error_msg = f"Failed to find political figures: {e}"
        return Command(
            update={
                "political_figures": [],
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )


@tool
async def search_political_commentary(
    query: str,
    politician: str,
    city: Annotated[str, InjectedState("city")],
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_results: int = 3,
) -> Command:
    """Search for political commentary and extract the politician's statements.

    Uses Tavily search with a political profile to find authoritative political
    content, then uses an LLM to extract the politician's actual commentary
    from each source. Returns unified results with politician name, source URL,
    and extracted comment.

    Args:
        query: The search query — e.g. "Austin mayor political commentary" or
               "John Smith city council news opinion".
        politician: The name of the politician to search commentary for.
        city: The city context for local political content (from state).
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        max_results: Maximum number of results to return (default 5).

    Returns:
        A Command object that updates the state with political commentary
        (containing politician, source_url, and comment).
    """
    try:
        raw_results = await search_political_content(
            query=query,
            city=city,
            max_results=max_results,
        )

        results = extract_search_results(raw_results)

        if not results:
            return Command(
                update={
                    "political_commentary": [],
                    "messages": [
                        ToolMessage(
                            content=f"No political commentary found for query '{query}'.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        political_commentary = []
        for r in results:
            url = r.get("url", "")
            extraction = await mcp_extract_commentary(
                url=url, politician=politician, query=query
            )
            political_commentary.append(
                {
                    "politician": politician,
                    "source_url": url,
                    "comment": extraction.get("commentary", ""),
                }
            )

        summary_lines = [
            f"Found {len(political_commentary)} commentary source(s) for {politician}:"
        ]
        for pc in political_commentary:
            comment_preview = (
                pc["comment"][:100] + "..."
                if len(pc["comment"]) > 100
                else pc["comment"]
            )
            summary_lines.append(f"  - {pc['source_url']}: {comment_preview}")

        return Command(
            update={
                "political_commentary": political_commentary,
                "messages": [
                    ToolMessage(
                        content="\n".join(summary_lines),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except ValueError as e:
        error_msg = f"Tavily API key not configured: {e}"
        return Command(
            update={
                "political_commentary": [],
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )
    except Exception as e:
        error_msg = f"Failed to search political commentary: {e}"
        return Command(
            update={
                "political_commentary": [],
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )


@tool
async def search_political_social_media(
    politician: str,
    city: Annotated[str, InjectedState("city")],
    research_context: Annotated[str | None, InjectedState("research_notes")],
    tool_call_id: Annotated[str, InjectedToolCallId],
    max_results: int = 10,
) -> Command:
    """Search for a politician's social media posts to gather additional context.

    IMPORTANT: This tool should ONLY be used when FAIRNESS and HOLISTIC understanding
    require more context about the politician's position. Before using this tool, consider
    whether the existing information is sufficient to provide a balanced view. This tool
    exists to ensure voters receive a complete picture, not to amplify any particular viewpoint.

    Use this tool when:
    - You need more context to be fair and balanced
    - The politician's official statements need verification
    - You want to understand their position on specific city issues

    Do NOT use this tool when:
    - You already have sufficient information from official sources
    - The purpose would be to find negative information
    - The information available is already fair and complete

    This tool searches Twitter/X for the politician's official account
    and retrieves their posts related to the city and research context.

    Args:
        politician: The full name of the politician to search for.
        city: The city context (from state).
        research_context: Additional context from research notes about what to search for.
        tool_call_id: Injected by LangGraph — used to associate the ToolMessage.
        max_results: Maximum number of tweets to retrieve (default 10).

    Returns:
        A Command object that updates the state with social media findings.
    """
    PREVIEW_MAX_LENGTH = 80

    if not politician or not politician.strip():
        return Command(
            update={
                "social_media_posts": [],
                "messages": [
                    ToolMessage(
                        content="Politician name is required for social media search.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    try:
        result = await mcp_search_tweets(
            politician_name=politician,
            city=city,
            research_context=research_context or "",
            max_results=max_results,
        )

        if result.get("error"):
            return Command(
                update={
                    "social_media_posts": [],
                    "messages": [
                        ToolMessage(
                            content=f"Twitter search failed: {result['error']}",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        tweets = result.get("tweets", [])
        user_found = result.get("user_found", False)

        if not tweets:
            return Command(
                update={
                    "social_media_posts": [],
                    "messages": [
                        ToolMessage(
                            content=f"No tweets found for {politician} related to {city}. "
                            "The politician may not have an active Twitter/X account.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        social_posts = []
        for tweet in tweets:
            social_posts.append(
                {
                    "politician": politician,
                    "platform": "twitter",
                    "tweet_id": tweet.get("id"),
                    "text": tweet.get("text"),
                    "created_at": tweet.get("created_at"),
                    "engagement": tweet.get("public_metrics", {}),
                }
            )

        summary_lines = [f"Found {len(social_posts)} tweet(s) from {politician}:"]
        for post in social_posts:
            text_preview = (
                post["text"][:PREVIEW_MAX_LENGTH] + "..."
                if len(post["text"]) > PREVIEW_MAX_LENGTH
                else post["text"]
            )
            summary_lines.append(f"  - {text_preview}")

        if not user_found:
            summary_lines.append(
                f"  Note: Could not verify official account. Results may include similar names."
            )

        return Command(
            update={
                "social_media_posts": social_posts,
                "messages": [
                    ToolMessage(
                        content="\n".join(summary_lines),
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )

    except Exception as e:
        error_msg = f"Failed to search Twitter: {type(e).__name__}"
        return Command(
            update={
                "social_media_posts": [],
                "messages": [ToolMessage(content=error_msg, tool_call_id=tool_call_id)],
            }
        )


# === AGENT CONSTRUCTION ===

_agent = BaseReActAgent(
    state_schema=PoliticalCommentaryState,
    tools=[
        political_figure_finder,
        search_political_commentary,
        search_political_social_media,
    ],
    system_prompt=political_commentary_sys_prompt,
)

political_commentary_agent = _agent.build()
