from langchain_core.tools import tool
from mcp.server.fastmcp import FastMCP

# -- Agent 1: Legislation Finder tools --
@tool
def web_search(query: str) -> str:
    """Search the web for legislation-related content."""
    # TODO: implement real search (e.g. Tavily, SerpAPI)
    return f"[stub] Search results for: {query}"


@tool
def url_fetcher(url: str) -> str:
    """Fetch raw HTML content from a URL."""
    # TODO: implement real HTTP fetch
    return f"[stub] Fetched content from: {url}"


@tool
def html_parser(html: str) -> str:
    """Parse raw HTML and extract structured text content."""
    # TODO: implement real HTML parsing (e.g. BeautifulSoup)
    return f"[stub] Parsed content from HTML ({len(html)} chars)"


# -- Agent 2: Scraper Builder tools --


@tool
def code_generator(description: str) -> str:
    """Generate Python scraping code based on a description."""
    # TODO: implement real code generation
    return f"[stub] Generated scraper code for: {description}"


@tool
def python_repl(code: str) -> str:
    """Execute Python code and return the output."""
    # TODO: implement sandboxed execution
    return f"[stub] Executed code ({len(code)} chars)"


@tool
def date_filter(data: str, days: int = 7) -> str:
    """Filter scraped data to only include items from the last N days."""
    # TODO: implement real date filtering
    return f"[stub] Filtered data to last {days} days"


# Tool lists for each agent
legislation_finder_tools = [web_search, url_fetcher]
agent_2_tools = [code_generator, python_repl, date_filter]
