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
    """Generate a grounded reflection on the current research progress using Wikidata context.

    Analyzes the conversation history, looks up organizations mentioned in sources
    on Wikidata, and produces a structured reflection identifying real gaps.

    Returns:
        A Command that updates the graph state by appending the reflection to reflection_list.
    """
    # Build a conversation summary from recent messages
    recent_messages = messages[-10:] if len(messages) > 10 else messages
    conversation_summary = "\n".join(
        f"{msg.type}: {msg.content[:500]}" for msg in recent_messages if msg.content
    )

    # Extract organization names from messages that mention URLs/sources
    org_names = set()
    for msg in messages:
        if not msg.content:
            continue
        content = msg.content
        if (
            "URL:" in content
            or "http" in content
            or ".gov" in content
            or ".org" in content
        ):
            extraction_response = _mini_model.invoke(
                [
                    {
                        "role": "system",
                        "content": "Extract organization names from this text. Return ONLY a JSON list of strings. If none found, return [].",
                    },
                    {"role": "user", "content": content[:1000]},
                ]
            )
            try:
                names = json.loads(extraction_response.content)
                if isinstance(names, list):
                    org_names.update(names)
            except (json.JSONDecodeError, TypeError):
                pass

    # Look up each org on Wikidata
    org_context_parts = []
    for org_name in list(org_names)[:8]:  # Cap at 8 to avoid excessive API calls
        entity_id = search_entity(org_name)
        if entity_id:
            classification = get_org_classification(entity_id)
            org_context_parts.append(
                f"- {org_name}: {classification.get('description', 'N/A')} | "
                f"Type: {', '.join(classification.get('instance_of', ['Unknown']))} | "
                f"Country: {classification.get('country', 'Unknown')}"
            )
        else:
            org_context_parts.append(f"- {org_name}: Not found on Wikidata")

    org_context = (
        "\n".join(org_context_parts)
        if org_context_parts
        else "No organizations identified yet."
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
                "content": "Produce a structured reflection based on the research so far.",
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
