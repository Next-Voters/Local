from contextlib import AsyncExitStack

from langchain_core.runnables import RunnableLambda

from config.constants import AGENT_RECURSION_LIMIT
from utils.schemas import ChainData
from utils.async_runner import run_async
from utils.mcp.tavily.client import managed_tavily_session
from utils.mcp.wikidata.client import managed_wikidata_session


async def _invoke_legislation_finder(city: str) -> dict:
    from agents.legislation_finder import legislation_finder_agent
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(managed_tavily_session())
        await stack.enter_async_context(managed_wikidata_session())
        return await legislation_finder_agent.ainvoke(
            {"city": city},
            config={"recursion_limit": AGENT_RECURSION_LIMIT},
        )


def run_legislation_finder(inputs: ChainData) -> ChainData:
    city = inputs.get("city", "Unknown")
    agent_result = run_async(lambda: _invoke_legislation_finder(city))
    legislation_sources = agent_result.get("reliable_legislation_sources", [])
    return {**inputs, "legislation_sources": legislation_sources}


legislation_finder_chain = RunnableLambda(run_legislation_finder)