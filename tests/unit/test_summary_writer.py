"""Unit tests for pipelines/node/summary_writer.py."""

from unittest.mock import MagicMock, patch


from pipelines.node.summary_writer import (
    _build_user_message,
    _normalize_source_urls,
    research_summary_writer,
)
from utils.schemas.pydantic import WriterOutput


# ---------------------------------------------------------------------------
# _normalize_source_urls
# ---------------------------------------------------------------------------


class TestNormalizeSourceUrls:
    def test_string_sources(self):
        assert _normalize_source_urls(["https://a.com", "https://b.com"]) == [
            "https://a.com",
            "https://b.com",
        ]

    def test_dict_sources(self):
        result = _normalize_source_urls([{"url": "https://a.com", "content": "x"}])
        assert result == ["https://a.com"]

    def test_mixed_list(self):
        result = _normalize_source_urls(["https://a.com", {"url": "https://b.com"}])
        assert result == ["https://a.com", "https://b.com"]

    def test_empty_returns_empty(self):
        assert _normalize_source_urls([]) == []

    def test_none_returns_empty(self):
        assert _normalize_source_urls(None) == []

    def test_strips_whitespace(self):
        result = _normalize_source_urls(["  https://a.com  "])
        assert result == ["https://a.com"]


# ---------------------------------------------------------------------------
# _build_user_message
# ---------------------------------------------------------------------------


class TestBuildUserMessage:
    def test_sources_block_present(self):
        msg = _build_user_message(["https://a.com"], ["Content A."], "Notes here.")
        assert "SOURCES:" in msg
        assert "1. https://a.com" in msg

    def test_notes_block_present(self):
        msg = _build_user_message(["https://a.com"], ["Content."], "Key notes.")
        assert "NOTES" in msg
        assert "Key notes." in msg

    def test_source_content_block_present(self):
        msg = _build_user_message(["https://a.com"], ["Page content block."], "notes")
        assert "SOURCE CONTENT" in msg
        assert "[Source 1]" in msg
        assert "Page content block." in msg

    def test_no_sources_shows_placeholder(self):
        msg = _build_user_message([], [], "notes")
        assert "(no sources)" in msg

    def test_empty_notes_shows_placeholder(self):
        msg = _build_user_message([], [], "")
        assert "(no notes)" in msg

    def test_skips_failed_content_blocks(self):
        msg = _build_user_message(
            ["https://a.com"],
            ["[Failed to fetch: 403]"],
            "notes",
        )
        assert "[Source 1]" not in msg
        assert "(no source content)" in msg

    def test_content_beyond_source_count_ignored(self):
        # Only 1 source URL, but 3 content blocks — only block 1 should appear
        msg = _build_user_message(
            ["https://a.com"],
            ["Block 1", "Block 2", "Block 3"],
            "notes",
        )
        assert "[Source 2]" not in msg
        assert "[Source 3]" not in msg

    def test_multiple_sources_numbered(self):
        msg = _build_user_message(
            ["https://a.com", "https://b.com"],
            ["Content A.", "Content B."],
            "notes",
        )
        assert "1. https://a.com" in msg
        assert "2. https://b.com" in msg


# ---------------------------------------------------------------------------
# research_summary_writer
# ---------------------------------------------------------------------------


def _run_summary_writer(inputs, writer_output):
    """Patch the structured LLM and run research_summary_writer."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = writer_output

    from pipelines.node.summary_writer import _get_model

    _get_model.cache_clear()
    with patch("pipelines.node.summary_writer.get_structured_llm", return_value=mock_llm):
        _get_model.cache_clear()
        return research_summary_writer(inputs)


class TestResearchSummaryWriter:
    def test_sets_legislation_summary_when_items_present(self, sample_writer_output):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_sources": ["https://toronto.ca"],
                    "legislation_content": ["Content."],
                    "notes": "Notes about housing bill.",
                }
            },
        }
        result = _run_summary_writer(inputs, sample_writer_output)
        assert result["topic_results"]["housing"]["legislation_summary"] is sample_writer_output

    def test_sets_none_when_writer_returns_empty_items(self):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_sources": [],
                    "legislation_content": [],
                    "notes": "Some notes.",
                }
            },
        }
        empty_output = WriterOutput(items=[])
        result = _run_summary_writer(inputs, empty_output)
        assert result["topic_results"]["housing"]["legislation_summary"] is None

    def test_sets_none_when_writer_returns_none(self):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_sources": [],
                    "legislation_content": [],
                    "notes": "notes",
                }
            },
        }
        result = _run_summary_writer(inputs, None)
        assert result["topic_results"]["housing"]["legislation_summary"] is None

    def test_multiple_topics_processed(self, sample_writer_output):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_sources": [],
                    "legislation_content": [],
                    "notes": "notes",
                },
                "transit": {
                    "topic_description": "Transit",
                    "legislation_sources": [],
                    "legislation_content": [],
                    "notes": "transit notes",
                },
            },
        }
        result = _run_summary_writer(inputs, sample_writer_output)
        # Both topics should have a legislation_summary key set
        assert "legislation_summary" in result["topic_results"]["housing"]
        assert "legislation_summary" in result["topic_results"]["transit"]

    def test_region_preserved_in_output(self, sample_writer_output):
        inputs = {
            "region": "san-diego",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_sources": [],
                    "legislation_content": [],
                    "notes": "notes",
                }
            },
        }
        result = _run_summary_writer(inputs, sample_writer_output)
        assert result["region"] == "san-diego"

    def test_returns_new_dict_not_mutation(self, sample_writer_output):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_sources": [],
                    "legislation_content": [],
                    "notes": "notes",
                }
            },
        }
        result = _run_summary_writer(inputs, sample_writer_output)
        assert result is not inputs
