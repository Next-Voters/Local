"""Region details tool — returns region-specific legislative context."""

from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from tools._helpers import ok
from utils.supabase_client import get_region_description


@tool
def region_details_tool(
    tool_call_id: Annotated[str, InjectedToolCallId],
    region: Annotated[str, InjectedState("region")],
) -> Command:
    """Look up region-specific legislative context (governing body, domains, portals, terminology).

    Call this once before dispatching researchers so you can include
    region-specific search guidance in each researcher_agent_tool call.
    """
    description = get_region_description(region)
    if not description:
        return ok(tool_call_id, f"No detailed info for {region}. Use general knowledge.")
    return ok(tool_call_id, description)
