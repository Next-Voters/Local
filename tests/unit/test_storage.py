"""Unit tests for utils/report/storage.py."""

from unittest.mock import MagicMock, patch

from utils.report.storage import (
    _normalize_source_urls,
    _resolve_source_urls,
    save_report,
)
from utils.schemas.pydantic import LegislationItem, WriterOutput

# ---------------------------------------------------------------------------
# _normalize_source_urls
# ---------------------------------------------------------------------------


class TestNormalizeSourceUrls:
    def test_string_sources(self):
        result = _normalize_source_urls(["https://toronto.ca", "https://legistar.com"])
        assert result == ["https://toronto.ca", "https://legistar.com"]

    def test_dict_sources(self):
        result = _normalize_source_urls([
            {"url": "https://toronto.ca", "content": "text"},
            {"url": "https://legistar.com", "content": "more text"},
        ])
        assert result == ["https://toronto.ca", "https://legistar.com"]

    def test_mixed_sources(self):
        result = _normalize_source_urls([
            "https://toronto.ca",
            {"url": "https://legistar.com", "content": "text"},
        ])
        assert result == ["https://toronto.ca", "https://legistar.com"]

    def test_strips_whitespace(self):
        result = _normalize_source_urls(["  https://toronto.ca  "])
        assert result == ["https://toronto.ca"]

    def test_empty_list(self):
        assert _normalize_source_urls([]) == []

    def test_none_input(self):
        assert _normalize_source_urls(None) == []

    def test_skips_empty_url_strings(self):
        result = _normalize_source_urls(["https://valid.com", "", "  "])
        assert result == ["https://valid.com"]

    def test_skips_dict_with_empty_url(self):
        result = _normalize_source_urls([{"url": "", "content": "x"}, {"url": "https://a.com"}])
        assert result == ["https://a.com"]


# ---------------------------------------------------------------------------
# _resolve_source_urls
# ---------------------------------------------------------------------------


class TestResolveSourceUrls:
    def test_valid_1based_indices(self):
        item = LegislationItem(header="h", bullets=[], cited_sources=[1, 3])
        urls = ["https://a.com", "https://b.com", "https://c.com"]
        result = _resolve_source_urls(item, urls)
        assert result == ["https://a.com", "https://c.com"]

    def test_out_of_bounds_index_skipped(self):
        item = LegislationItem(header="h", bullets=[], cited_sources=[1, 99])
        urls = ["https://a.com"]
        result = _resolve_source_urls(item, urls)
        assert result == ["https://a.com"]

    def test_zero_index_skipped(self):
        item = LegislationItem(header="h", bullets=[], cited_sources=[0])
        urls = ["https://a.com"]
        result = _resolve_source_urls(item, urls)
        assert result == []

    def test_no_cited_sources(self):
        item = LegislationItem(header="h", bullets=[], cited_sources=[])
        urls = ["https://a.com"]
        assert _resolve_source_urls(item, urls) == []

    def test_empty_urls_with_indices(self):
        item = LegislationItem(header="h", bullets=[], cited_sources=[1])
        assert _resolve_source_urls(item, []) == []


# ---------------------------------------------------------------------------
# save_report
# ---------------------------------------------------------------------------


def _make_supabase_mock(report_id=42):
    """Build a mock Supabase client that returns report_id on upsert."""
    client = MagicMock()
    upsert_response = MagicMock()
    upsert_response.data = [{"id": report_id}]
    (
        client.table.return_value
        .upsert.return_value
        .execute.return_value
    ) = upsert_response
    return client


class TestSaveReport:
    def test_returns_none_when_summary_missing(self):
        result = save_report("toronto", "housing", {})
        assert result is None

    def test_returns_none_when_summary_is_none(self):
        result = save_report("toronto", "housing", {"legislation_summary": None})
        assert result is None

    def test_returns_none_when_summary_items_empty(self):
        summary = WriterOutput(items=[])
        result = save_report("toronto", "housing", {"legislation_summary": summary})
        assert result is None

    def test_returns_none_when_topic_id_not_found(self):
        summary = WriterOutput(items=[LegislationItem(header="h", bullets=["b"], cited_sources=[])])
        with patch("utils.report.storage._get_topic_id", return_value=None):
            result = save_report("toronto", "housing", {"legislation_summary": summary})
        assert result is None

    def test_returns_report_id_on_success(self):
        summary = WriterOutput(items=[LegislationItem(header="h", bullets=["b"], cited_sources=[])])
        client = _make_supabase_mock(report_id=99)
        with (
            patch("utils.report.storage._get_topic_id", return_value=7),
            patch("utils.report.storage.get_supabase_client", return_value=client),
        ):
            result = save_report(
                "toronto",
                "housing",
                {
                    "legislation_summary": summary,
                    "legislation_sources": ["https://toronto.ca"],
                },
            )
        assert result == 99

    def test_upserts_report_row(self):
        summary = WriterOutput(items=[LegislationItem(header="h", bullets=["b"], cited_sources=[])])
        client = _make_supabase_mock()
        with (
            patch("utils.report.storage._get_topic_id", return_value=1),
            patch("utils.report.storage.get_supabase_client", return_value=client),
        ):
            save_report("toronto", "housing", {"legislation_summary": summary})

        client.table.assert_any_call("reports")

    def test_inserts_report_headers(self):
        summary = WriterOutput(items=[LegislationItem(header="h", bullets=["b"], cited_sources=[])])
        client = _make_supabase_mock()
        with (
            patch("utils.report.storage._get_topic_id", return_value=1),
            patch("utils.report.storage.get_supabase_client", return_value=client),
        ):
            save_report("toronto", "housing", {"legislation_summary": summary})

        client.table.assert_any_call("report_headers")

    def test_returns_none_on_supabase_exception(self):
        summary = WriterOutput(items=[LegislationItem(header="h", bullets=["b"], cited_sources=[])])
        client = MagicMock()
        client.table.side_effect = Exception("connection refused")
        with (
            patch("utils.report.storage._get_topic_id", return_value=1),
            patch("utils.report.storage.get_supabase_client", return_value=client),
        ):
            result = save_report("toronto", "housing", {"legislation_summary": summary})
        assert result is None
