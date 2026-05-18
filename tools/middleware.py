"""Agent middleware for the NV Local pipeline.

Provides reusable middleware components that can be composed with
create_agent's middleware parameter.
"""

from typing import Callable

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import SystemMessage

from config.constants import MAX_REFLECTION_ENTRIES
from utils.schemas import ReflectionEntry

_REFLECTION_PREAMBLE = (
    "Here are previous reflections. Use as context to drive your "
    "next actions/decisions:\n\n"
)


class ReflectionMiddleware(AgentMiddleware):
    """Injects reflection history into agent context before each LLM call.

    Reads ``reflection_list`` from agent state and prepends formatted
    reflections to the system message. Notes are NOT injected here — they
    live directly in the messages list as SystemMessage objects (added by
    note_taker, removed by delete_note via RemoveMessage).
    """

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Prepend reflections to the system prompt before each LLM call."""
        reflection_list: list[ReflectionEntry] = (
            getattr(request.state, "reflection_list", None)
            or request.state.get("reflection_list", [])
            if hasattr(request.state, "get")
            else []
        )

        if not reflection_list:
            return handler(request)

        if len(reflection_list) > MAX_REFLECTION_ENTRIES:
            reflection_list = reflection_list[-MAX_REFLECTION_ENTRIES:]

        entries = []
        for r in reflection_list:
            gaps = ", ".join(r.gaps_identified) if r.gaps_identified else "None"
            entries.append(
                f"- {r.reflection}\n  Gaps: {gaps}\n  Next action: {r.next_action}"
            )
        reflection_section = _REFLECTION_PREAMBLE + "\n".join(entries)

        # Prepend to existing system message
        if request.system_message:
            new_content = reflection_section + "\n\n" + request.system_message.content
            new_sys = SystemMessage(content=new_content)
        else:
            new_sys = SystemMessage(content=reflection_section)

        return handler(request.override(system_message=new_sys))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Async version — must await the async handler."""
        reflection_list: list[ReflectionEntry] = (
            getattr(request.state, "reflection_list", None)
            or request.state.get("reflection_list", [])
            if hasattr(request.state, "get")
            else []
        )

        if not reflection_list:
            return await handler(request)

        if len(reflection_list) > MAX_REFLECTION_ENTRIES:
            reflection_list = reflection_list[-MAX_REFLECTION_ENTRIES:]

        entries = []
        for r in reflection_list:
            gaps = ", ".join(r.gaps_identified) if r.gaps_identified else "None"
            entries.append(
                f"- {r.reflection}\n  Gaps: {gaps}\n  Next action: {r.next_action}"
            )
        reflection_section = _REFLECTION_PREAMBLE + "\n".join(entries)

        if request.system_message:
            new_content = reflection_section + "\n\n" + request.system_message.content
            new_sys = SystemMessage(content=new_content)
        else:
            new_sys = SystemMessage(content=reflection_section)

        return await handler(request.override(system_message=new_sys))
