"""Political commentary agent for NV Local.

This module defines the political_commentry_agent that finds political figures
and their blog commentary for a given city. It uses the BaseReActAgent template
with political figure finder and blog search tools.

The agent helps voters identify relevant political figures and their publicly
available commentary on local issues.
"""

from dotenv import load_dotenv

from agents.base_agent_template import BaseReActAgent
from tools.political_commentry_finder import (
    political_figure_finder,
    search_political_commentary,
)

from utils.schemas import PoliticalCommentaryState

load_dotenv()

# === AGENT CONSTRUCTION ===

_agent = BaseReActAgent(
    state_schema=PoliticalCommentaryState,
    tools=[political_figure_finder, search_political_commentary],
    system_prompt="You are a political commentary agent that helps find and analyze political figures and their blogs.",
)

political_commentry_agent = _agent.build()
