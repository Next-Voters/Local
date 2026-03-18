import httpx

from langchain_core.runnables import RunnableLambda

from utils.schemas import ChainData


def run_content_retrieval(inputs: ChainData) -> ChainData:
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


content_retrieval_chain = RunnableLambda(run_content_retrieval)
