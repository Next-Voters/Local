import httpx
from dotenv import load_dotenv
from typing import TypedDict, NotRequired

from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from agents.legislation_finder import legislation_finder_agent
from utils.models import WriterOutput
from utils.prompts import writer_sys_prompt

load_dotenv()

model = ChatOpenAI(model="gpt-4o-mini")

class LegislationContent(TypedDict):
    source: str
    content: str
    error: NotRequired[str]

class ChainData(TypedDict):
    city: NotRequired[str]
    legislation_sources: NotRequired[str]
    legislation_content: NotRequired[list[LegislationContent]]
    final_output: NotRequired[WriterOutput]

def run_legislation_finder(inputs: ChainData) -> ChainData:
    """Run the legislation finder agent as a node."""
    city = inputs.get("city", "Unknown")
    agent_result = legislation_finder_agent.invoke({"messages": [], "city": city})
    legislation_sources = agent_result.get("messages", [])
    return {"legislation_sources": legislation_sources}


def run_content_retrieval(inputs: ChainData) -> ChainData:
    """Fetch content from legislation sources."""
    legislation_sources = inputs.get("legislation_sources", [])
    legislation_content = []

    for source in legislation_sources:
        try:
            markdown_url = f"https://markdown.new/{source}"
            response = httpx.get(markdown_url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            legislation_content.append(
                {"source": source, "content": response.text}
            )
        except httpx.HTTPError as e:
            legislation_content.append(
                {"source": source, "content": None, "error": str(e)}
            )

    return {"legislation_content": legislation_content}

def writer(inputs: ChainData) -> ChainData:
    """Generate final output using LLM with structured output."""
    agent_conversation = inputs.get("legislation_content", [])
    notes = agent_conversation[-1] if agent_conversation else None
    system_prompt = writer_sys_prompt.format("")

    structured_model = model.with_structured_output(WriterOutput)

    response: WriterOutput = structured_model.invoke(
        [{"role": "system", "content": system_prompt}] + ([notes] if notes else []),
    )

    return {"final_output": response}


chain = (
    RunnableLambda(run_legislation_finder)
    | RunnableLambda(run_content_retrieval)
    | RunnableLambda(writer)
)


if __name__ == "__main__":
    city = str(input("What city would you like to find legislation in? "))

    result = chain.invoke({"city": city})

    print("\n=== NV Local Results ===\n")
    agent_output = result.get("final_output") if result.get("final_output") else None
    print(agent_output)
