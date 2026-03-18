from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData


def run_legislation_finder(inputs: ChainData) -> ChainData:
    from agents.legislation_finder import legislation_finder_agent

    city = inputs.get("city", "Unknown")

    agent_result = legislation_finder_agent.invoke({"city": city})

    legislation_sources = agent_result.get("reliable_legislation_sources", [])

    return {**inputs, "legislation_sources": legislation_sources}


legislation_finder_chain = RunnableLambda(run_legislation_finder)
