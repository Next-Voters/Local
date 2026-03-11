from langgraph.prebuilt import create_react_agent, create_supervisor_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# ---- LLM ----
llm = ChatOpenAI(model="gpt-4o-mini")

# ---- Example Tool ----
@tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

tools = [add_numbers]

# ---- Worker Agents ----
worker_agent_1 = create_react_agent(
    llm=llm,
    tools=tools,
    name="worker_agent_a",
    system_prompt="You solve problems and use tools when needed."
)

worker_agent_2 = create_react_agent(
    llm=llm,
    tools=tools,
    name="worker_agent_b",
    system_prompt="You solve problems and use tools when needed."
)

# ---- Supervisor Agent ----
supervisor = create_supervisor_agent(
    llm=llm,
    agents=[worker_agent_1, worker_agent_2],
    system_prompt="You decide which agent should handle the task."
)

# ---- Run Graph ----
graph = supervisor.compile()

result = graph.invoke({
    "messages": [
        {"role": "user", "content": "What is 5 + 7?"}
    ]
})

print(result)
