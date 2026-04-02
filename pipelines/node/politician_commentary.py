from contextlib import AsyncExitStack

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda

from config.constants import AGENT_RECURSION_LIMIT
from utils.schemas import ChainData
from utils.async_runner import run_async
from utils.mcp.tavily.client import managed_tavily_session
from utils.mcp.political_figures.client import managed_political_figures_session


async def _invoke_political_commentary(
    city: str, topic: str, research_notes: str
) -> dict:
    """Invoke the political commentary agent with full pipeline context."""
    from agents.political_commentary_finder import political_commentary_agent

    task_message = f"Research political commentary for {city}"
    if topic:
        task_message += f" on the topic of: {topic}"

    async with AsyncExitStack() as stack:
        await stack.enter_async_context(managed_tavily_session())
        await stack.enter_async_context(managed_political_figures_session())
        return await political_commentary_agent.ainvoke(
            {
                "city": city,
                "topic": topic,
                "research_notes": research_notes,
                "messages": [HumanMessage(content=task_message)],
            },
            config={"recursion_limit": AGENT_RECURSION_LIMIT},
        )


def run_politician_commentary_finder(inputs: ChainData) -> ChainData:
    """Run the political commentary agent and merge results into pipeline state."""
    city = inputs.get("city", "Unknown")
    topic = inputs.get("topic", "")
    research_notes = inputs.get("notes", "")
    agent_result = run_async(
        lambda: _invoke_political_commentary(city, topic, research_notes)
    )
    political_commentary = agent_result.get("political_commentary", [])
    social_media_posts = agent_result.get("social_media_posts", [])
    return {
        **inputs,
        "politician_public_statements": political_commentary,
        "social_media_posts": social_media_posts,
    }


politician_commentary_chain = RunnableLambda(run_politician_commentary_finder)