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

from pipelines.node.legislation_finder import legislation_finder_chain
from pipelines.node.content_retrieval import content_retrieval_chain
from pipelines.node.note_taker import note_taker_chain
from pipelines.node.summary_writer import summary_writer_chain
from pipelines.node.politician_commentary import politician_commentary_chain
from pipelines.node.report_formatter import report_formatter_chain
from pipelines.node.email_sender import send_email_to_subscribers

chain = (
    legislation_finder_chain
    | content_retrieval_chain
    | note_taker_chain
    | summary_writer_chain
    | politician_commentary_chain
    | report_formatter_chain
    | send_email_to_subscribers
)


def run_pipeline(city: str) -> str:
    """Execute the full NV Local pipeline and return the markdown report."""
    result = chain.invoke({"city": city})
    return result.get("markdown_report", "")
