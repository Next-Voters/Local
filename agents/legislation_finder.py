from datetime import datetime, timedelta

from typing import NotRequired, Annotated

import operator

from utils.agents import BaseAgentState, BaseReActAgent
from utils.prompts import legislation_finder_sys_prompt
from tools.legislation_finder import web_search, reliability_analysis


# === STATE DEFINITION ===


class LegislationFinderState(BaseAgentState):
    """Agent-specific state for the legislation finder agent."""

    city: NotRequired[str]
    raw_legislation_sources: NotRequired[Annotated[list[str], operator.add]]
    reliable_legislation_sources: NotRequired[Annotated[list[str], operator.add]]


# === AGENT CONSTRUCTION ===

_agent = BaseReActAgent(
    state_schema=LegislationFinderState,
    tools=[web_search, reliability_analysis],
    system_prompt=lambda state: legislation_finder_sys_prompt.format(
        input_city=state.get("city", "Unknown"),
        last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d"),
        today=datetime.today().strftime("%B %d"),
    ),
)

legislation_finder_agent = _agent.build()
