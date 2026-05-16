"""Agent system prompts."""

from config.system_prompts.lead_researcher import lead_researcher_sys_prompt
from config.system_prompts.legislation_finder import (
    legislation_finder_subagent_sys_prompt,
    legislation_finder_sys_prompt,
)
from config.system_prompts.note_taker import note_taker_sys_prompt
from config.system_prompts.reflection import reflection_prompt
from config.system_prompts.writer import writer_sys_prompt

__all__ = [
    "lead_researcher_sys_prompt",
    "legislation_finder_subagent_sys_prompt",
    "legislation_finder_sys_prompt",
    "note_taker_sys_prompt",
    "reflection_prompt",
    "writer_sys_prompt",
]
