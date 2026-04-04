from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData


def _safe_text(value: object, fallback: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        return text or fallback
    return fallback


def report_formatter(inputs: ChainData) -> ChainData:
    legislation_summary = inputs.get("legislation_summary")
    public_statements = inputs.get("politician_public_statements") or []

    if legislation_summary is None:
        return {
            **inputs,
            "markdown_report": "# No Legislation Found\n\nNo recent legislation was found for the specified city. Try a different city or check back later for updates.",
        }

    title = _safe_text(legislation_summary.title, "Untitled Report")
    summary = _safe_text(legislation_summary.summary, "No summary available.")
    body = _safe_text(legislation_summary.body, "No detailed report available.")

    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Full Report",
        "",
        body,
        "",
        "---",
        "",
        "## Politician Public Statements",
        "",
    ]

    if not isinstance(public_statements, list) or not public_statements:
        lines.append("### Coming Soon!")
        lines.append("")

    for statement in public_statements:
        if not isinstance(statement, dict):
            continue

        politician_name = _safe_text(
            statement.get("politician") or statement.get("name"), "Unknown Politician"
        )
        source_link = _safe_text(
            statement.get("source_url") or statement.get("source"), "N/A"
        )
        commentary = _safe_text(
            statement.get("comment") or statement.get("summary"),
            "No statement summary available.",
        )

        lines.append(f"### {politician_name}")
        lines.append("")
        lines.append(f"**Source:** {source_link}")
        lines.append("")
        lines.append(commentary)
        lines.append("")

        statement_summaries = statement.get("statement_summaries")
        if not isinstance(statement_summaries, list):
            continue

        for item in statement_summaries:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"**Legislation Source Link:** {_safe_text(item.get('source'), 'N/A')}"
            )
            lines.append("")
            lines.append(_safe_text(item.get("summary"), "No summary available."))
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Citations")
    lines.append("")

    legislation_sources = inputs.get("legislation_sources") or []
    if legislation_sources:
        for i, source in enumerate(legislation_sources, start=1):
            url = source.get("url") if isinstance(source, dict) else source
            if isinstance(url, str) and url.strip():
                lines.append(f"{i}. {url.strip()}")
        lines.append("")
    else:
        lines.append("No sources available.")
        lines.append("")

    markdown_report = "\n".join(lines)

    return {**inputs, "markdown_report": markdown_report}


report_formatter_chain = RunnableLambda(report_formatter)
