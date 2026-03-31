from contextlib import AsyncExitStack

from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData
from utils.async_runner import run_async
from utils.mcp.tavily.client import managed_tavily_session
from utils.mcp.political_figures.client import managed_political_figures_session


async def _invoke_political_commentary(city: str) -> dict:
    from agents.political_commentary_finder import political_commentary_agent
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(managed_tavily_session())
        await stack.enter_async_context(managed_political_figures_session())
        return await political_commentary_agent.ainvoke({"city": city})


def run_politician_commentary_finder(inputs: ChainData) -> ChainData:
    city = inputs.get("city", "Unknown")
    agent_result = run_async(lambda: _invoke_political_commentary(city))
    political_commentary = agent_result.get("political_commentary", [])
    return {**inputs, "politician_public_statements": political_commentary}


politician_commentary_chain = RunnableLambda(run_politician_commentary_finder)