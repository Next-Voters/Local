# Next Voters Local

NV Local is a Python CLI that runs a small, multi-step research pipeline per city:

1) discover recent municipal legislation sources
2) fetch the linked pages and extract text
3) turn the text into dense notes and a structured summary
4) format a markdown report
5) optionally email the report to subscribers (Supabase + SMTP)

Docs:
- `docs/ARCHITECTURE.md`
- `docs/OPERATIONS.md`
- `CONTRIBUTING.md`

## Features

- Multi-city execution (one pipeline per city, run concurrently)
- Legislation discovery via Brave Search (MCP) with Goggles rules
- Source vetting via Wikidata lookups + an LLM-based classifier
- Markdown report output (stdout and/or `-o` to file)
- Optional email delivery (Supabase subscription list + SMTP)

## Architecture At A Glance

- Entry points: `python main.py` (plain stdout) or `python run_cli_main.py` (Rich console)
- Pipeline: `pipelines/nv_local.py` composes a fixed chain of nodes
- Agents: LangGraph ReAct-style agents for legislation discovery and political commentary
- LLM steps: note-taking and summary writing are single-call LLM transforms
- External services: OpenAI (LLM), Brave Search (web search), Wikidata (org classification), `markdown.new` (HTML -> markdown-ish extraction), optional Supabase + SMTP

## Prerequisites

- Python 3.10+
- An OpenAI API key (used by `langchain-openai`)
- A Brave Search API key (used via Smithery-hosted MCP)
- Optional: Twitter API credentials (for the social-media tool)
- Optional: Supabase + SMTP credentials (to email reports)

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure environment variables:

```bash
cp .env.example .env
```

Notes:
- `python main.py` does not call `load_dotenv()`. Export env vars in your shell, or use the Rich wrapper (`python run_cli_main.py`) which loads `.env`.
- The default cities are hard-coded in `data/__init__.py` as `SUPPORTED_CITIES`.

Run:

```bash
python main.py
```

Save output:

```bash
python main.py -o out/report.md
```

Quiet mode:

```bash
python main.py -q -o out/report.md
```

## Configuration

Required for the core pipeline:

- `OPENAI_API_KEY`: OpenAI key used by `langchain-openai`
- `BRAVE_SEARCH_API_KEY`: used by `utils/mcp/brave_client.py` to call the Smithery Brave Search MCP server

Optional:

- `TWITTER_API_KEY`, `TWITTER_BEARER_TOKEN`: enable the Twitter/X MCP client used by the political commentary tools
- `SUPABASE_URL`, `SUPABASE_KEY`: used to load subscriber emails from the `subscriptions` table
- `SMTP_EMAIL`, `SMTP_APP_PASSWORD`: used to send HTML emails via SMTP (default host: `smtp.gmail.com:587`)

## Common Tasks

- Change the cities the CLI runs: edit `data/__init__.py` (`SUPPORTED_CITIES`)
- Build and run the container:
  ```bash
  docker build -t next-voters-local -f docker/Dockerfile .
  docker run --rm \
    -e OPENAI_API_KEY \
    -e BRAVE_SEARCH_API_KEY \
    next-voters-local
  ```

## Troubleshooting

- Brave search failures: ensure `BRAVE_SEARCH_API_KEY` is set; the error originates in `utils/mcp/brave_client.py`
- OpenAI auth errors: ensure `OPENAI_API_KEY` is set in the environment seen by the process
- Empty or thin reports: the pipeline only summarizes what it can fetch; some sites may block scraping or fail via `markdown.new`
- Email not sent: the email step is skipped unless all of `SMTP_EMAIL`, `SMTP_APP_PASSWORD`, `SUPABASE_URL`, `SUPABASE_KEY` are set

## License

MIT: see `LICENSE`.
