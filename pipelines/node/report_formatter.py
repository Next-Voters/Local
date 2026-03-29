from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData


def report_formatter(inputs: ChainData) -> ChainData:
    legislation_summary = inputs.get("legislation_summary")
    public_statements = inputs.get("politician_public_statements") or []

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


report_formatter_chain = RunnableLambda(report_formatter)
