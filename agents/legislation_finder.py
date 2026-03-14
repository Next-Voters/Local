from datetime import datetime, timedelta

from base_agent_template import BaseReActAgent
from tools.legislation_finder import web_search, reliability_analysis

from utils.typed_dicts import LegislationFinderState
from utils.prompts import legislation_finder_sys_prompt


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
