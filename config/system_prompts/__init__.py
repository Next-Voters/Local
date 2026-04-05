"""Agent system system_prompts."""

from config.system_prompts.compression import compression_instruction
from config.system_prompts.legislation_finder import legislation_finder_sys_prompt
from config.system_prompts.note_taker import note_taker_sys_prompt
from config.system_prompts.reflection import reflection_prompt
from config.system_prompts.writer import writer_sys_prompt

__all__ = [
    "compression_instruction",
    "legislation_finder_sys_prompt",
    "note_taker_sys_prompt",
    "reflection_prompt",
    "writer_sys_prompt",
]
