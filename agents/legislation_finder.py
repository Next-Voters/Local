from datetime import datetime, timedelta
from dotenv import load_dotenv

from agents.base_agent_template import BaseReActAgent
from tools.legislation_finder import web_search, reliability_analysis

from utils.schemas import LegislationFinderState
from utils.prompts import legislation_finder_sys_prompt

load_dotenv()

# === AGENT CONSTRUCTION ===

_agent = BaseReActAgent(
    state_schema=LegislationFinderState,
    tools=[web_search, reliability_analysis],
    system_prompt=lambda state: legislation_finder_sys_prompt.format(
        input_city=state.get("city", "Unknown"),
        last_week_date=(datetime.today() - timedelta(days=7)).strftime("%B %d, %Y"),
        today=datetime.today().strftime("%B %d, %Y"),
    ),
)

legislation_finder_agent = _agent.build()
