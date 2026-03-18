# Next Voters Local

> **Hold your local representative accountable to their actions**  
> An intelligent multi-agent deep research system that investigates municipal legislation, extracts politician positions, and presents factual, bias-resistant information to voters.

<div align="center">

[![GitHub License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[Features](#-features) • [Getting Started](#-getting-started) • [How It Works](#-how-it-works) • [Architecture](#-architecture) • [Contributing](#-contributing)

</div>

---

## 🎯 Features

- **🔍 Intelligent Legislation Discovery** — Autonomous web search for recent municipal legislation with Wikidata-backed source validation
- **📊 Bias-Resistant Analysis** — Five-layer debiasing strategy grounded in academic research (Gallegos et al., 2024; Phute et al., 2023)
- **🗳️ Politician Position Extraction** — Scrapes and analyzes politician statements, press releases, and voting records
- **🛡️ Identity Protection** — Anonymizes politician names before bias analysis, ensuring fair rhetoric evaluation
- **📝 Factual Summaries** — Generates clean, digestible summaries backed by authoritative sources
- **⚙️ Modular Agent System** — Composable ReAct agents with clear separation of concerns
- **🌐 Wikidata Integration** — Validates source reliability using structured knowledge about organizations

---

## 🚀 Quick Start

### Prerequisites

- **Python** 3.10+
- **OpenAI API Key** (for GPT-4, GPT-4o-mini)
- **Tavily API Key** (for web search)
- **Git**

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/hemitoncode/Next-Voters-Local.git
   cd Next-Voters-Local
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure API keys**
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI and Tavily API keys
   ```

5. **Run the system**
   ```bash
   python main.py
   ```
   Enter a city name (e.g., "Austin", "Toronto") to investigate recent municipal legislation.

---
### Key Design Principles

1. **Minimal Agency** — ReAct agents only where unpredictable targets or retry loops exist such as during legislative activity discovery phase. Everything else is a deterministic LLM call or pure code.
2. **No Supervision** — Sequential DAG, no supervisor node. Routing is always the same; routing costs would waste API calls.
3. **Judge Isolation** — The Judge never sees real names, never sees graph state. Its narrow scope is its strength.
4. **Source Authority** — Only `.gov`, `.gc.ca`, and Wikidata-validated organizations pass reliability checks. No blogs, no opinion sites, no partisan media.
5. **Cite or Reject** — Every claim must cite its source. Unsupported inferences are rejected.

### Technology Stack

| Component | Technology |
|-----------|-----------|
| **Orchestration** | LangChain Expression Language |
| **LLM Provider** | OpenAI (GPT-4, GPT-4o-mini) |
| **LLM Framework** | LangChain 1.1+ |
| **Web Search** | Tavily Search API |
| **Organization Lookup** | Wikidata REST API + SPARQL |
| **Web Scraping** | Generated Python code (REPL sandbox) |
| **NER / Anonymization** | spaCy (or equivalent) |
| **Config** | python-dotenv |
| **HTTP Client** | httpx |

---

## 🛡️ Bias Resistance

Next Voters Local implements **two core safeguards** against bias:

| Safeguard | Where | Method |
|-----------|-------|--------|
| **LLM-as-a-Defense: Name Anonymizer** | Anonymizer (LLM) | Use language model to identify & replace politician names before any analysis |
| **Source Reliability Measure** | Legislation Finder | Validate organizations via Wikidata to ensure only unbiased, authoritative sources are used |

### Implementation

- **Name Anonymization** — All politician identities are removed before rhetoric analysis. This prevents the LLM from making identity-based inferences.
- **Source Validation** — Every source is checked against Wikidata for organizational classification. Only `.gov`, `.gc.ca`, and nonpartisan organizations pass through. No blogs, opinion sites, or politically-aligned media.

### Responsible Use

This system is designed for **informational purposes only**. Users should:
- ✅ Verify claims using the provided source URLs
- ✅ Cross-reference multiple sources before forming opinions
- ✅ Understand this tool supplements, not replaces, civic engagement
- ❌ Not rely on a single summary for critical decisions

## 📝 Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes** with clear commit messages
4. **Test** locally: `python main.py`
5. **Submit a Pull Request** with a description of changes

#### ⚠️ Note: You are not entitled to payment for your services. You are also not affiliated with Next Voters, and you may not claim any titles of employment within the organization. 

### Reporting Issues

Found a bug? Please open an [issue](https://github.com/hemitoncode/Next-Voters-Local/issues) with:
- Clear description of the problem
- Steps to reproduce
- Expected vs. actual behavior
- Python version & OS

---

## 📚 References & Inspiration

This project is informed by academic research on LLM bias and debiasing:

- **Gallegos et al., 2024** — [Bias and Fairness in Large Language Models: A Survey](https://arxiv.org/abs/2402.01981) — Two-pass self-debiasing strategy (Layer 3)
- **Phute et al., 2023** — [LLM Self Defense](https://arxiv.org/abs/2308.07308) — Judge-as-LLM design (Layer 4)
- **OpenNorth** — [Canadian municipal representative data](https://opennorth.ca/)

---

## 🤝 Acknowledgments

- Built with [LangGraph](https://langchain-ai.github.io/langgraph/) for orchestration
- Source validation powered by [Wikidata](https://www.wikidata.org/)
- Search via [Tavily](https://www.tavily.com/)
- LLM backbone: [OpenAI](https://openai.com/)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) — see the LICENSE file for details.

---

## 💬 Contact & Support

- **Issues & Discussions**: [GitHub Issues](https://github.com/hemitoncode/Next-Voters-Local/issues)
- **Questions?** Check [CLAUDE.md](/.claude/CLAUDE.md) for development documentation

---

<div align="center">

**Empowering voters with factual, bias-resistant information about local legislation.**

Made with ❤️ by Next Voters

</div>
