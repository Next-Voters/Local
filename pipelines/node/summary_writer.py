from functools import lru_cache

from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData, WriterOutput
from utils.llm import get_structured_llm
from config.system_prompts import writer_sys_prompt


@lru_cache(maxsize=1)
def _get_model():
    return get_structured_llm(WriterOutput)


def _normalize_source_urls(legislation_sources) -> list[str]:
    """Extract URLs from legislation_sources (mix of strings and dicts), preserving order."""
    urls: list[str] = []
    for source in legislation_sources or []:
        if isinstance(source, dict):
            url = source.get("url", "").strip()
        elif isinstance(source, str):
            url = source.strip()
        else:
            url = ""
        if url:
            urls.append(url)
    return urls


def _build_user_message(
    source_urls: list[str],
    legislation_content: list[str],
    notes: str,
) -> str:
    """Assemble the SOURCES / SOURCE CONTENT / NOTES blocks the writer prompt expects.

    Source numbers are 1-based and align with the order rendered by the
    report formatter, so [N] markers in the output correlate with the
    final report's "Sources" list.
    """
    if source_urls:
        sources_block = "\n".join(f"{i}. {url}" for i, url in enumerate(source_urls, start=1))
    else:
        sources_block = "(no sources)"

    content_blocks: list[str] = []
    for i, block in enumerate(legislation_content or [], start=1):
        if i > len(source_urls):
            break
        text = (block or "").strip()
        if not text or text.startswith("[Failed to fetch:"):
            continue
        content_blocks.append(f"[Source {i}]\n{text}")
    source_content = "\n\n".join(content_blocks) if content_blocks else "(no source content)"

    return (
        "SOURCES:\n"
        f"{sources_block}\n\n"
        "SOURCE CONTENT:\n"
        f"{source_content}\n\n"
        "NOTES:\n"
        f"{notes or '(no notes)'}"
    )


def research_summary_writer(inputs: ChainData) -> ChainData:
    notes = inputs.get("notes")
    source_urls = _normalize_source_urls(inputs.get("legislation_sources"))
    legislation_content = inputs.get("legislation_content") or []

    user_message = _build_user_message(source_urls, legislation_content, notes or "")

    # Static system prompt keeps the prefix stable across invocations so
    # GPT-5 can cache it; the per-run sources/content/notes go in the user message.
    ai_generated_summary: WriterOutput = _get_model().invoke(
        [
            {"role": "system", "content": writer_sys_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    if ai_generated_summary is None or not ai_generated_summary.items:
        return {**inputs, "legislation_summary": None}

    return {**inputs, "legislation_summary": ai_generated_summary}


summary_writer_chain = RunnableLambda(research_summary_writer)
