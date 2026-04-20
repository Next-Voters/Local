from functools import lru_cache

from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData
from utils.llm import get_llm
from config.system_prompts import note_taker_sys_prompt


@lru_cache(maxsize=1)
def _get_model():
    return get_llm()


def research_note_taker(inputs: ChainData) -> ChainData:
    raw_content_list = inputs.get("legislation_content", [])

    if not raw_content_list:
        return {**inputs, "notes": "No legislation content found."}

    raw_content = "\n".join(raw_content_list)

    # Keep the system prompt static across invocations so GPT-5 can cache
    # its ~4K-token prefix (~50% discount on cache hits). Dynamic page
    # content moves to the user message tail.
    ai_generated_notes = _get_model().invoke(
        [
            {"role": "system", "content": note_taker_sys_prompt},
            {"role": "user", "content": f"Raw page content to distill:\n\n{raw_content}"},
        ],
    )

    return {**inputs, "notes": str(ai_generated_notes.content)}


note_taker_chain = RunnableLambda(research_note_taker)
