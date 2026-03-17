"""Shared tools available to all ReAct agents."""

import json
from typing import Annotated
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langchain_openai import ChatOpenAI
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from utils.schemas import ReflectionEntry
from utils.prompts import reflection_prompt

load_dotenv()

_mini_model = ChatOpenAI(
    model="gpt-5-mini", temperature=0.0, max_tokens=1500, timeout=30
)


@tool
def reflection_tool(
    tool_call_id: Annotated[str, InjectedToolCallId],
    messages: Annotated[list[BaseMessage], InjectedState("messages")],
) -> Command:
    """Reflects on conversation history to determine the next action."""

    recent_messages = messages[-10:] if len(messages) > 10 else messages
    conversation_summary = "\n".join(
        f"{msg.type}: {msg.content[:500]}" for msg in recent_messages if msg.content
    )

    formatted_prompt = reflection_prompt.format(
        conversation_summary=conversation_summary,
    )
    response = _mini_model.invoke(
        [
            {"role": "system", "content": formatted_prompt},
            {
                "role": "user",
                "content": "Produce a structured reflection based on the past conversation",
            },
        ]
    )

    # Parse the structured reflection
    try:
        reflection_data = json.loads(response.content)
        entry = ReflectionEntry(
            reflection=reflection_data.get(
                "reflection", "Unable to produce reflection."
            ),
            gaps_identified=reflection_data.get("gaps_identified", []),
            next_action=reflection_data.get("next_action", "Continue searching."),
        )
    except (json.JSONDecodeError, TypeError):
        entry = ReflectionEntry(
            reflection=response.content[:500],
            gaps_identified=[],
            next_action="Continue searching with more specific queries.",
        )

    return Command(
        update={
            "reflection_list": [entry],
            "messages": [
                ToolMessage(content=entry.next_action, tool_call_id=tool_call_id)
            ],
        }
    )
