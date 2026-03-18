"""Legislation finder agent for NV Local.

This module defines the legislation_finder_agent that researches local legislation
for a given city. It uses the BaseReActAgent template with web search and
reliability analysis tools.

The agent searches for recent local legislation and evaluates source reliability.
It uses a dynamic system prompt that incorporates the target city and date range.
"""

from datetime import datetime, timedelta

from agents.base_agent_template import BaseReActAgent
from tools.legislation_finder import web_search, reliability_analysis

from utils.schemas import LegislationFinderState
from config.system_prompts import legislation_finder_sys_prompt

# === AGENT CONSTRUCTION ===

_agent = BaseReActAgent(
    state_schema=LegislationFinderState,
    tools=[
        web_search,
        reliability_analysis
    ],
    system_prompt=lambda state: legislation_finder_sys_prompt.format(
        input_city=state.get("city", "Unknown"),
        last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d, %Y"),
        today=datetime.today().strftime("%B %d, %Y"),
    ),
)

legislation_finder_agent = _agent.build()
