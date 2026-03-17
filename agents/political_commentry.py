from dotenv import load_dotenv

from agents.base_agent_template import BaseReActAgent
from tools.political_commentry import political_figure_finder, blog_search

from utils.schemas import PoliticalCommentaryState

load_dotenv()

# === AGENT CONSTRUCTION ===

_agent = BaseReActAgent(
    state_schema=PoliticalCommentaryState,
    tools=[political_figure_finder, blog_search],
    system_prompt="You are a political commentary agent that helps find and analyze political figures and their blogs.",
)

political_commentry_agent = _agent.build()
