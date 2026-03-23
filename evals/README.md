# NV Local Evaluation Suite

Comprehensive evaluation suite for the NV Local municipal legislation research pipeline using DeepEval.

## Overview

This evaluation suite provides automated testing and quality assessment for all NV Local components:

- **LegislationFinderAgent**: Finds relevant municipal legislation with reliability analysis
- **SummaryWriter**: Creates structured summaries using Pydantic schema (WriterOutput)
- **PoliticalCommentaryAgent**: Identifies political figures and their public statements
- **ReportFormatter**: Generates well-structured markdown reports
- **End-to-End Pipeline**: Complete pipeline from discovery to report

## Installation

```bash
pip install deepeval pytest pytest-asyncio

# Or install from requirements
pip install -r requirements.txt
```

## Project Structure

```
evals/
├── metrics/
│   ├── __init__.py
│   ├── legislation_accuracy.py    # Legislation relevance metrics
│   ├── summary_quality.py          # Summary quality metrics
│   ├── political_relevance.py      # Political figure relevance
│   ├── report_formatting.py        # Markdown structure validation
│   └── no_hallucination.py         # Hallucination detection
├── test_legislation_finder.py      # Unit tests for legislation finder
├── test_summary_writer.py          # Unit tests for summary writer
├── test_political_commentary.py    # Unit tests for political commentary
├── test_report_formatter.py        # Unit tests for report formatter
├── test_e2e_pipeline.py            # End-to-end integration tests
├── conftest.py                     # Pytest fixtures and mocks
└── README.md                       # This file
```

## Running Tests

### Run All Tests

```bash
cd /Users/hemitpatel/PycharmProjects/Next-Voters-Local
pytest evals/ -v
```

### Run Specific Test Files

```bash
# Unit tests for individual components
pytest evals/test_legislation_finder.py -v
pytest evals/test_summary_writer.py -v
pytest evals/test_political_commentary.py -v
pytest evals/test_report_formatter.py -v

# End-to-end integration tests
pytest evals/test_e2e_pipeline.py -v
```

### Run with Coverage

```bash
pytest evals/ -v --cov=evals --cov-report=html
```

## Custom Metrics

### Available Metrics

| Metric | File | Purpose |
|--------|------|---------|
| `LegislationAccuracyMetric` | `metrics/legislation_accuracy.py` | Measures relevance of discovered legislation to city |
| `SummaryQualityMetric` | `metrics/summary_quality.py` | Evaluates factual accuracy and completeness of summaries |
| `PoliticalRelevanceMetric` | `metrics/political_relevance.py` | Measures relevance of political figures to city |
| `ReportFormattingMetric` | `metrics/report_formatting.py` | Validates markdown report structure |
| `NoHallucinationMetric` | `metrics/no_hallucination.py` | Detects hallucinated content |

### Using Custom Metrics

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase
from deepeval import evaluate

from evals.metrics.legislation_accuracy import create_legislation_accuracy_metric
from evals.metrics.summary_quality import create_summary_quality_metric
from evals.metrics.report_formatting import create_report_formatting_metric

# Create metrics with custom thresholds
legislation_metric = create_legislation_accuracy_metric(threshold=0.75)
summary_metrics = create_summary_quality_metric(threshold=0.8, multi_dimensional=True)
formatting_metrics = create_report_formatting_metric(threshold=0.7)

# Combine all metrics
all_metrics = [
    *legislation_metric,
    *summary_metrics,
    *formatting_metrics,
]

# Create test cases
test_cases = [
    LLMTestCase(
        input="Find Toronto legislation",
        actual_output="Found Bill 1-2024: Climate Action Initiative",
        retrieval_context="Source: Toronto City Council\nBill 1-2024 passed 38-7",
    ),
]

# Run evaluation
results = evaluate(test_cases=test_cases, metrics=all_metrics)
```

### Detailed Metrics

Some metrics have extended versions with sub-scores:

```python
from evals.metrics.legislation_accuracy import DetailedLegislationAccuracyMetric

metric = DetailedLegislationAccuracyMetric(
    city_relevance_weight=0.5,
    legislative_authenticity_weight=0.25,
    source_credibility_weight=0.25,
    threshold=0.75,
)
```

## Fixtures and Mocks

The `conftest.py` provides fixtures for testing:

### Test Data Fixtures

- `mock_city`: "Toronto"
- `mock_city_nyc`: "New York City"
- `mock_city_san_diego`: "San Diego"
- `sample_legislation_sources`: Toronto legislation sources
- `sample_legislation_sources_nyc`: NYC legislation sources
- `sample_legislation_content`: Full legislation text
- `sample_legislation_notes`: Compressed notes
- `sample_writer_output`: WriterOutput schema instance
- `sample_politician_data`: Political figure data
- `sample_political_statements`: Political statements
- `sample_markdown_report`: Complete markdown report
- `mock_retrieval_context`: Source context for evaluation

### Mock API Fixtures

- `mock_brave_search`: Mock Brave Search API responses
- `mock_wikidata`: Mock Wikidata API responses
- `mock_llm_response`: Mock LLM responses
- `mock_structured_llm_response`: Mock structured LLM output
- `patch_brave_search`: Monkeypatch for Brave Search
- `patch_wikidata`: Monkeypatch for Wikidata

### State Fixtures

- `mock_agent_state`: Mock agent state for testing
- `mock_chain_data`: Mock chain data for pipeline testing

## Test Cases

### Legislation Finder Tests

```python
class TestLegislationFinderAgent:
    def test_agent_initialization(self)
    def test_web_search_finds_relevant_sources(self)
    def test_reliability_analysis_scores_sources(self)
    def test_full_agent_workflow(self)
    def test_city_specific_search_queries(self)
```

### Summary Writer Tests

```python
class TestSummaryWriter:
    def test_writer_output_schema_validation(self)
    def test_summary_writer_produces_valid_schema(self)
    def test_summary_writer_handles_no_content(self)

class TestSummaryQualityMetric:
    def test_high_quality_summary(self)
    def test_incomplete_summary(self)
    def test_biased_summary(self)
```

### Political Commentary Tests

```python
class TestPoliticalCommentaryAgent:
    def test_agent_initialization(self)
    def test_political_figure_finder_tool(self)
    def test_commentary_search_tool(self)

class TestPoliticalRelevanceMetric:
    def test_highly_relevant_politicians(self)
    def test_irrelevant_politicians(self)
```

### Report Formatter Tests

```python
class TestReportFormatter:
    def test_formatter_initialization(self)
    def test_report_formatter_with_valid_input(self)
    def test_report_includes_required_sections(self)

class TestReportFormattingMetric:
    def test_well_formatted_report(self)
    def test_missing_sections(self)
```

### End-to-End Tests

```python
class TestEndToEndPipeline:
    def test_pipeline_produces_markdown_report(self)
    def test_pipeline_handles_multiple_cities(self)

class TestPipelineIntegration:
    def test_full_pipeline_with_mocks(self)
    def test_pipeline_output_quality_metrics(self)
```

## Scoring Guidelines

### Legislation Accuracy

| Score | Description |
|-------|-------------|
| 1.0 | All sources are highly relevant to city and represent actual legislation |
| 0.8 | Most sources relevant, minor issues |
| 0.6 | Mixed relevance, some non-municipal sources |
| 0.4 | Few relevant sources, mostly wrong jurisdiction |
| 0.0 | No relevant legislation sources found |

### Summary Quality

| Score | Description |
|-------|-------------|
| 1.0 | Excellent factual accuracy, completeness, clarity, and objectivity |
| 0.8 | Minor issues in one dimension |
| 0.6 | Noticeable issues in 2+ dimensions |
| 0.4 | Significant gaps in accuracy or completeness |
| 0.0 | Completely inaccurate or useless summary |

### Political Relevance

| Score | Description |
|-------|-------------|
| 1.0 | All figures highly relevant, statements address legislation |
| 0.8 | Most figures relevant, statements connect to issues |
| 0.6 | Mixed relevance, some off-topic |
| 0.4 | Few relevant figures, mostly generic |
| 0.0 | No relevant figures or statements |

### Report Formatting

| Score | Description |
|-------|-------------|
| 1.0 | Perfect structure, all sections present, clean markdown |
| 0.85 | Minor formatting issues, all sections present |
| 0.7 | Most sections present, some problems |
| 0.5 | Missing major sections, formatting issues |
| 0.0 | Completely unstructured |

## CI/CD Integration

Add to your CI pipeline:

```yaml
# .github/workflows/eval.yml
name: Evaluation

on: [push, pull_request]

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install deepeval pytest pytest-asyncio pytest-cov
      
      - name: Run evaluations
        run: pytest evals/ -v --tb=short
        
      - name: Upload coverage
        uses: codecov/codecov-action@v4
```

## Troubleshooting

### Common Issues

**Issue**: `ModuleNotFoundError: No module named 'deepeval'`

```bash
pip install deepeval
```

**Issue**: Mock API calls not working

Ensure you're patching the correct module path. Check imports in the source files.

**Issue**: LLM evaluation is slow

Set `OPENAI_API_KEY` environment variable and consider using `gpt-4o-mini` for faster evaluation.

## Contributing

When adding new tests:

1. Follow the existing test structure in each file
2. Use fixtures from `conftest.py`
3. Add appropriate `@pytest.mark` decorators
4. Include both positive and negative test cases
5. Test edge cases (empty inputs, special characters, etc.)

## License

Part of NV Local project.
