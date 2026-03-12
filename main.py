from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from utils.agent import build_agent_1, build_agent_2

llm = ChatOpenAI(model="gpt-4o-mini")

# Build agents
agent_1 = build_agent_1(llm)
agent_2 = build_agent_2(llm)

# Node functions — each invokes an agent and returns updated messages
def run_agent_1(state: MessagesState) -> MessagesState:
    result = agent_1.invoke({"messages": state["messages"]})
    return {"messages": result["messages"]}


def run_agent_2(state: MessagesState) -> MessagesState:
    result = agent_2.invoke({"messages": state["messages"]})
    return {"messages": result["messages"]}


graph_builder = StateGraph(MessagesState)
graph_builder.add_node("legislation_finder", run_agent_1)
graph_builder.add_node("scraper_builder", run_agent_2)

graph_builder.add_edge(START, "legislation_finder")
graph_builder.add_edge("legislation_finder", "scraper_builder")
graph_builder.add_edge("scraper_builder", END)

graph = graph_builder.compile()

# Run
if __name__ == "__main__":
    result = graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Find recent Canadian legislation from the last 7 days.",
                }
            ]
        }
    )

    # Print final messages
    for msg in result["messages"]:
        print(f"\n[{msg.type}]: {msg.content[:200] if msg.content else '(tool call)'}")
