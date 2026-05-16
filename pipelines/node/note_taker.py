"""Note taker pipeline node.

Generates dense research notes per topic from the retrieved legislation content.
"""

import logging
from functools import lru_cache

from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData
from utils.llm import get_llm
from config.system_prompts import note_taker_sys_prompt

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model():
    """Return a cached LLM instance."""
    return get_llm()


def research_note_taker(inputs: ChainData) -> ChainData:
    """Generate research notes for each topic's legislation content."""
    topic_results = inputs.get("topic_results", {})

    for topic, result in topic_results.items():
        raw_content_list = result.get("legislation_content", [])

        if not raw_content_list:
            result["notes"] = "No legislation content found."
            continue

        raw_content = "\n".join(raw_content_list)

        logger.info("Generating notes for topic: %s", topic)
        ai_generated_notes = _get_model().invoke(
            [
                {"role": "system", "content": note_taker_sys_prompt},
                {"role": "user", "content": f"Raw page content to distill:\n\n{raw_content}"},
            ],
        )

        result["notes"] = str(ai_generated_notes.content)

    return {**inputs, "topic_results": topic_results}


note_taker_chain = RunnableLambda(research_note_taker)
