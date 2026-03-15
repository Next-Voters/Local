"""Shared tools available to all ReAct agents."""

import json
from typing import Annotated

from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt.tool_node import InjectedState
from langgraph.types import Command

from utils.models import ReflectionEntry
from utils.prompts import reflection_prompt
from utils.wikidata_client import search_entity, get_org_classification

_mini_model = ChatOpenAI(
    model="gpt-5-mini", temperature=0.0, max_tokens=1500, timeout=30
)


@tool
def reflection_tool(
    messages: Annotated[list[BaseMessage], InjectedState("messages")],
) -> Command:
    f"""
You are a reflection tool embedded in a multi-step research pipeline. Your job \
is to reason carefully over the full conversation history provided to you — \
including every tool call and its response — and produce a structured assessment \
that will guide the next decision in the pipeline.

## Conversation history:
{messages}

---

## Your task

Work through the following chain of thought before producing your output:

1. **Inventory what has been attempted**
   List every distinct action taken so far such as searches run, entities looked up, \
   APIs called, and the key result or outcome of each.

2. **Identify what has been established**
   State the facts or conclusions that are now well-supported by the evidence \
   gathered. Be specific — vague summaries are not useful.

3. **Identify what is still unknown or uncertain**
   List the concrete gaps: information that was sought but not found, questions \
   that remain unanswered, ambiguities that could lead the pipeline in the wrong \
   direction.

4. **Diagnose failure patterns (if any)**
   Note if the same query or lookup has been attempted more than once with \
   similar results, if the pipeline appears to be looping, or if a strategy is \
   clearly not yielding useful signal.

5. **Determine the single best next action**
   Based on the gaps and the context, decide what one action would most advance \
   progress. Be specific: name the tool to call, the exact query or entity to \
   use, and why this is the highest-value next step. This must be a concrete \
   instruction the agent can act on immediately.

Rules:
- next_action must be a single, specific instruction. Never write "continue \
searching" or "try again" without specifying exactly what to search for and why.
- gaps_identified must be concrete missing facts, not vague observations like \
"more research needed".
- If everything needed is already known, set next_action to "Compile final \
answer from established facts: <brief summary of what to include>".
- Do not invent facts. Only reference information present in the conversation history.
    """
    # Build a conversation summary from recent messages
    recent_messages = messages[-10:] if len(messages) > 10 else messages
    conversation_summary = "\n".join(
        f"{msg.type}: {msg.content[:500]}" for msg in recent_messages if msg.content
    )

    # Call LLM with reflection prompt
    formatted_prompt = reflection_prompt.format(
        conversation_summary=conversation_summary,
        org_context=org_context,
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

    return Command(update={"reflection_list": [entry]})
