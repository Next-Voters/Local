from dotenv import load_dotenv
from typing import TypedDict, NotRequired
from pydantic import BaseModel, Field

from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

from agents.legislation_finder import legislation_finder_agent
from utils.prompts import writer_sys_prompt

load_dotenv()

model = ChatOpenAI(model="gpt-4o-mini")

class WriterOutput(BaseModel):
    title: str = Field(description="Title of the written content")
    body: str = Field(description="Main written content")
    summary: str = Field(description="Brief summary of the content")

class AgentOrchestrationState(TypedDict):
    """State for the agent orchestration graph."""
    city: NotRequired[str]
    agent_conversation: NotRequired[list[BaseMessage]]
    final_output: NotRequired[list[WriterOutput]]



def run_legislation_finder(state: AgentOrchestrationState) -> AgentOrchestrationState:
    """Run the legislation finder agent as a subgraph node."""
    city = state.get("city", "Unknown")
    agent_result = legislation_finder_agent.invoke({"messages": [], "city": city})
    agent_messages = agent_result.get("messages", [])
    return {"agent_conversation": agent_messages}


def run_agent_2(state: AgentOrchestrationState) -> AgentOrchestrationState:
    """Placeholder for the second agent (scraper builder)."""
    # agent_response = agent_2.invoke({"messages": state["agent_conversation"]})
    # return {"agent_conversation": agent_response["messages"]}

    # Temporary placeholder
    return {"agent_conversation": state.get("agent_conversation", [])}

def writer(state: AgentOrchestrationState) -> AgentOrchestrationState:
    notes = state.get("agent_conversation", [])[-1]
    system_prompt = writer_sys_prompt.format("")

    structured_model = model.with_structured_output(WriterOutput)

    response: WriterOutput = structured_model.invoke(
        [{"role": "system", "content": system_prompt}] + notes,
    )

    return {"final_output": response}

graph_builder = StateGraph(AgentOrchestrationState)
graph_builder.add_node("legislation_finder", run_legislation_finder)
graph_builder.add_node("scraper_builder", run_agent_2)
graph_builder.add_node("writer", writer)

graph_builder.add_edge(START, "legislation_finder")
graph_builder.add_edge("legislation_finder", "scraper_builder")
graph_builder.add_edge("scraper_builder", "writer")
graph_builder.add_edge("writer", END)

graph = graph_builder.compile()

# Run
if __name__ == "__main__":
    city = str(input("What city would you like to find legislation in? "))

    result = graph.invoke(
        {
            "agent_conversation": [],
            "city": city,
        }
    )

    # Print final messages
    print("\n=== Legislation Finder Results ===\n")

    agent_output = result.get("final_output") if result.get("final_output") else None
    print(agent_output)