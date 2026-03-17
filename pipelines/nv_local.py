"""Main pipeline orchestration for NV Local voter education tool.

This module defines the LangGraph pipeline for researching local legislation
and generating markdown reports. It chains together the legislation finder
agent, content retrieval, note-taking, summary writing, and report formatting.

Key functions:
    run_legislation_finder: Invokes the legislation finder agent to get sources.
    run_content_retrieval: Fetches markdown content from legislation URLs.
    research_note_taker: Analyzes legislation content and creates notes.
    research_summary_writer: Generates structured summary using LLM.
    report_formatter: Formats final markdown report.
    run_pipeline: Executes the full pipeline for a given city.

The pipeline uses a RunnableLambda-based chain that passes data between
stages via a ChainData dictionary.
"""

import httpx
from dotenv import load_dotenv

from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI

from agents.legislation_finder import legislation_finder_agent
from agents.political_commentry_finder import political_commentry_agent

from utils.schemas import WriterOutput, ChainData
from config.system_prompts import writer_sys_prompt, note_taker_sys_prompt

load_dotenv()

model = ChatOpenAI(model="gpt-4o-mini")


def run_legislation_finder(inputs: ChainData) -> ChainData:
    """Run the legislation finder agent as a node."""
    city = inputs.get("city", "Unknown")

    agent_result = legislation_finder_agent.invoke({"city": city})

    legislation_sources = agent_result.get("reliable_legislation_sources", [])

    return {**inputs, "legislation_sources": legislation_sources}


def run_content_retrieval(inputs: ChainData) -> ChainData:
    """Fetch content from legislation sources."""
    legislation_sources = inputs.get("legislation_sources", [])

    legislation_content = []

    for source in legislation_sources:
        url = source.get("url") if isinstance(source, dict) else source

        if not url:
            legislation_content.append(f"[Invalid source: {source}]")
            continue

        try:
            markdown_url = f"https://markdown.new/{url}"
            response = httpx.get(markdown_url, timeout=30, follow_redirects=True)
            response.raise_for_status()
            legislation_content.append(response.text)
        except httpx.HTTPError:
            legislation_content.append(f"[Failed to fetch: {url}]")

    return {**inputs, "legislation_content": legislation_content}


def research_note_taker(inputs: ChainData) -> ChainData:
    """Analyze legislation content and create notes."""
    raw_content_list = inputs.get("legislation_content", [])

    if not raw_content_list:
        return {**inputs, "notes": "No legislation content found."}

    raw_content = "\n".join(raw_content_list)

    system_prompt = note_taker_sys_prompt.format(raw_content=raw_content)

    ai_generated_notes = model.invoke(
        [{"role": "system", "content": system_prompt}],
    )

    return {**inputs, "notes": str(ai_generated_notes.content)}


def research_summary_writer(inputs: ChainData) -> ChainData:
    """Generate final output using LLM with structured output."""
    notes = inputs.get("notes")

    system_prompt = writer_sys_prompt.format(notes=notes)

    structured_model = model.with_structured_output(WriterOutput)

    ai_generated_summary: WriterOutput = structured_model.invoke(
        [{"role": "system", "content": system_prompt}],
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


def run_politician_commentry_finder(inputs: ChainData) -> ChainData:
    """Run the legislation finder agent as a node."""

    agent_result = political_commentry_agent.invoke({"city": city})

    legislation_sources = agent_result.get("reliable_legislation_sources", [])

    return {**inputs, "legislation_sources": legislation_sources}


def report_formatter(inputs: ChainData) -> ChainData:
    """Format a final report using the legislative summary and the politician public statements."""
    legislation_summary = inputs.get("legislation_summary")
    public_statements = inputs.get("politician_public_statements")

    if legislation_summary is None:
        return {
            **inputs,
            "markdown_report": "# No Legislation Found\n\nNo recent legislation was found for the specified city. Try a different city or check back later for updates.",
        }

    lines = [
        f"# {legislation_summary.title}",
        "",
        "## Summary",
        "",
        legislation_summary.summary,
        "",
        "## Full Report",
        "",
        legislation_summary.body,
        "",
        "---",
        "",
        "## Politician Public Statements",
        "### Coming Soon!",
        "",
    ]

    for politician in public_statements:
        lines.append(f"### {politician['name']}")
        lines.append("")
        for statement in politician["statement_summaries"]:
            lines.append(f"**Legislation Source Link:** {statement['source']}")
            lines.append("")
            lines.append(statement["summary"])
            lines.append("")

    markdown_report = "\n".join(lines)

    return {**inputs, "markdown_report": markdown_report}


chain = (
    RunnableLambda(run_legislation_finder)
    | RunnableLambda(run_content_retrieval)
    | RunnableLambda(research_note_taker)
    | RunnableLambda(research_summary_writer)
    | RunnableLambda(run_politician_commentry_finder)
    | RunnableLambda(report_formatter)
)


def run_pipeline(city: str) -> str:
    """Execute the full NV Local pipeline and return the markdown report."""
    result = chain.invoke({"city": city})
    return result.get("markdown_report", "")
