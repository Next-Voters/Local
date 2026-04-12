"""Legislation finder agent for NV Local.

Searches for recent local legislation for a given city using web search,
and creates Google Calendar events for legislative dates via a remote MCP server.
"""

import logging
import os
from datetime import datetime, timedelta

from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agents.base_agent_template import BaseReActAgent
from config.system_prompts import legislation_finder_sys_prompt
from utils.tools import web_search
from utils.schemas import LegislationFinderState

logger = logging.getLogger(__name__)

_GCAL_MCP_URL = "https://gcal.mintmcp.com/mcp"


async def _load_gcal_tools():
    """Load calendar tools from the remote Google Calendar MCP server."""
    headers = {}
    token = os.getenv("MINTMCP_AUTH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    read, write, _ = await streamablehttp_client(
        _GCAL_MCP_URL, headers=headers
    ).__aenter__()
    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()
    tools = await load_mcp_tools(session)
    return tools
async def build_legislation_finder():
    """Build the legislation finder agent with web_search + remote create_event."""
    
    gcal_tools = await _load_gcal_tools()
    target_gcal_tools_name = {"create_event", "get_calendar_events", "update_event"}
    selected_gcal_tools = [t for t in gcal_tools if t.name in target_gcal_tools_name]
    
    agent = BaseReActAgent(
        state_schema=LegislationFinderState,
        tools=[web_search, ] + selected_gcal_tools,
        system_prompt=lambda state: legislation_finder_sys_prompt.format(
            input_city=state.get("city", "Unknown"),
            last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d, %Y"),
            today=datetime.today().strftime("%B %d, %Y"),
        ),
    )
    return agent.build()
