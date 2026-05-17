"""City details tool — looks up city-specific legislative context.

Gives the lead researcher governing body names, official domains,
legislative portal URLs, and local terminology so it can craft
targeted search_guidance for each researcher subagent.
"""

from typing import Annotated

from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from tools._helpers import ok
from utils.supabase_client import get_region_details


@tool
def city_details_tool(
    tool_call_id: Annotated[str, InjectedToolCallId],
    region: Annotated[str, InjectedState("region")],
) -> Command:
    """Look up city-specific legislative context (governing body, official domains, portals, terminology).

    Call this once before dispatching researchers so you can include
    city-specific search guidance in each researcher_agent_tool call.
    """
    details = get_region_details(region)
    if not details:
        return ok(tool_call_id, f"No detailed info for {region}. Use general knowledge.")

    parts = [
        f"Region: {details['region']} ({details['state']})",
        f"Governing body: {details['governing_body']}",
        f"Official website: {details['official_website']}",
    ]
    if details.get("legislative_portal"):
        parts.append(f"Legislative portal: {details['legislative_portal']}")
    if details.get("legistar_domain"):
        parts.append(f"Legistar: {details['legistar_domain']}")
    if details.get("legislative_terms"):
        parts.append(f"Terminology: {', '.join(details['legislative_terms'])}")
    if details.get("population_context"):
        parts.append(f"Context: {details['population_context']}")
    if details.get("notes"):
        parts.append(f"Notes: {details['notes']}")

    return ok(tool_call_id, "\n".join(parts))
