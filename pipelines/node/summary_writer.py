"""Summary writer pipeline node.

Extracts structured legislation items (header + bullets) per topic from
the research notes and source content.
"""

from functools import lru_cache

from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData, WriterOutput
from utils.llm import get_structured_llm
from utils.logger import get_logger
from config.system_prompts import writer_sys_prompt

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_model():
    """Return a cached structured LLM instance."""
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
    findings: list[dict] | None = None,
) -> str:
    """Assemble the SOURCES / SOURCE CONTENT / NOTES / FINDINGS blocks the writer prompt expects."""
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

    if findings:
        findings_lines = []
        for f in sorted(findings, key=lambda x: x.get("priority", 99)):
            headline = f.get("headline", "untitled")
            bullets = f.get("summary", [])
            sources = f.get("sources", [])
            lines = [f"[{f.get('priority', '?')}] {headline}"]
            for b in bullets:
                lines.append(f"    - {b}")
            if sources:
                lines.append(f"    Sources: {', '.join(sources)}")
            findings_lines.append("\n".join(lines))
        findings_block = "\n\n".join(findings_lines)
    else:
        findings_block = "(no pre-structured findings)"

    return (
        "SOURCES:\n"
        f"{sources_block}\n\n"
        "SOURCE CONTENT:\n"
        f"{source_content}\n\n"
        "NOTES:\n"
        f"{notes or '(no notes)'}\n\n"
        "PRE-STRUCTURED FINDINGS (UNFILTERED by topic — apply your Topic Scope gate to every finding before including it; use as scaffold ONLY for on-topic items):\n"
        f"{findings_block}"
    )


def research_summary_writer(inputs: ChainData) -> ChainData:
    """Generate structured legislation summaries for each topic."""
    topic_results = inputs.get("topic_results", {})

    for topic, result in topic_results.items():
        notes = result.get("notes")
        source_urls = _normalize_source_urls(result.get("legislation_sources"))
        legislation_content = result.get("legislation_content") or []
        topic_description = result.get("topic_description", "")

        findings = result.get("findings")
        user_message = _build_user_message(source_urls, legislation_content, notes or "", findings)

        formatted_prompt = (
            writer_sys_prompt
            .replace("{topic}", topic)
            .replace("{topic_description}", topic_description)
        )

        logger.info("Generating summary for topic: %s", topic)
        ai_generated_summary: WriterOutput = _get_model().invoke(
            [
                {"role": "system", "content": formatted_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        if ai_generated_summary is None or not ai_generated_summary.items:
            result["legislation_summary"] = None
        else:
            result["legislation_summary"] = ai_generated_summary

    return {**inputs, "topic_results": topic_results}


summary_writer_chain = RunnableLambda(research_summary_writer)
