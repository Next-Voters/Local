# Next Voters Local

Next Voters uses AI agents to find, research, and summarize municipal legislation — making government information accessible to communities that cannot afford the time or resources to track what their local officials are doing.

Many people — working families, elderly residents, anyone already stretched thin — are effectively locked out of the legislative process simply because keeping up with city council agendas is a full-time job. Next Voters automates that work so you don't have to.

## What It Does

- **Discovers** recent legislation across multiple cities using AI-powered web search
- **Researches** each piece of legislation with specialized AI agents that classify sources, extract key details, and provide political context
- **Summarizes** everything into clear, readable reports so anyone can understand what's happening in their city

## Architecture At A Glance

Next Voters is a multi-agent research pipeline. Each run discovers legislation sources, fetches and extracts content, and produces a structured summary — all orchestrated by LangGraph-based agents. It runs as standalone software via CLI or Docker container.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Operations](docs/OPERATIONS.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT: see `LICENSE`.
