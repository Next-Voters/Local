from functools import lru_cache

from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData, WriterOutput
from utils.llm import get_structured_llm
from config.system_prompts import writer_sys_prompt


@lru_cache(maxsize=1)
def _get_model():
    return get_structured_llm(WriterOutput)


def research_summary_writer(inputs: ChainData) -> ChainData:
    notes = inputs.get("notes")

    # Static system prompt keeps the prefix stable across invocations so
    # GPT-5 can cache it; the per-run notes go in the user message.
    ai_generated_summary: WriterOutput = _get_model().invoke(
        [
            {"role": "system", "content": writer_sys_prompt},
            {"role": "user", "content": f"Research notes to transform:\n\n{notes or ''}"},
        ],
    )

    if ai_generated_summary is None:
        return {**inputs, "legislation_summary": None}

    title_lower = (
        ai_generated_summary.title.lower().strip() if ai_generated_summary.title else ""
    )
    no_title_patterns = ("no content", "no recent", "no legislation", "none", "")

    if (
        title_lower in no_title_patterns
        or title_lower.startswith("no ")
        or title_lower.startswith("n/a")
    ):
        return {**inputs, "legislation_summary": None}

    return {**inputs, "legislation_summary": ai_generated_summary}


summary_writer_chain = RunnableLambda(research_summary_writer)
