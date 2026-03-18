from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData


def run_politician_commentary_finder(inputs: ChainData) -> ChainData:
    from agents.political_commentry_finder import political_commentry_agent

    city = inputs.get("city", "Unknown")

    agent_result = political_commentry_agent.invoke({"city": city})

    political_commentary = agent_result.get("political_commentary", [])

    return {**inputs, "politician_public_statements": political_commentary}


politician_commentary_chain = RunnableLambda(run_politician_commentary_finder)
