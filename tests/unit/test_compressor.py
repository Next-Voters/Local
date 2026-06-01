"""Unit tests for utils/content/compressor.py."""

from unittest.mock import patch

from config.constants import COMPRESSION_RATE, MIN_CHARS_TO_COMPRESS
from utils.content.compressor import compress_text

SHORT_TEXT = "Short."  # well below MIN_CHARS_TO_COMPRESS
LONG_TEXT = "x " * (MIN_CHARS_TO_COMPRESS + 100)  # guaranteed above the threshold


class TestShortTextBypass:
    def test_empty_string_returned_unchanged(self):
        assert compress_text("") == ""

    def test_below_threshold_returned_unchanged(self):
        text = "A" * (MIN_CHARS_TO_COMPRESS - 1)
        assert compress_text(text) == text

    def test_at_threshold_calls_pruner(self):
        # len == MIN_CHARS_TO_COMPRESS is NOT below threshold → pruner is invoked.
        text = "B" * MIN_CHARS_TO_COMPRESS
        with patch("utils.content.pruner.prune_text", return_value="pruned") as mock_prune:
            result = compress_text(text)
        mock_prune.assert_called_once()
        assert result == "pruned"

    def test_pruner_not_called_for_short_text(self):
        text = "Too short."
        with patch("utils.content.pruner.prune_text") as mock_prune:
            result = compress_text(text)
        mock_prune.assert_not_called()
        assert result == text


class TestNormalCompression:
    def test_delegates_to_prune_text(self):
        expected = "compressed output"
        with patch("utils.content.pruner.prune_text", return_value=expected) as mock_prune:
            result = compress_text(LONG_TEXT, rate=0.5, query="housing")
        assert result == expected
        mock_prune.assert_called_once_with(LONG_TEXT, rate=0.5, query="housing")

    def test_default_rate_passed_through(self):
        # compress_text calls: prune_text(text, rate=rate, query=query)
        with patch("utils.content.pruner.prune_text", return_value="out") as mock_prune:
            compress_text(LONG_TEXT)
        assert mock_prune.call_args.kwargs["rate"] == COMPRESSION_RATE

    def test_query_none_by_default(self):
        # compress_text calls: prune_text(text, rate=rate, query=query)
        with patch("utils.content.pruner.prune_text", return_value="out") as mock_prune:
            compress_text(LONG_TEXT)
        assert mock_prune.call_args.kwargs["query"] is None


class TestFallbackTruncation:
    def test_falls_back_to_head_truncation_on_pruner_error(self):
        with patch("utils.content.pruner.prune_text", side_effect=RuntimeError("model unavailable")):
            result = compress_text(LONG_TEXT, rate=0.5)
        target = max(MIN_CHARS_TO_COMPRESS, int(len(LONG_TEXT) * 0.5))
        assert result == LONG_TEXT[:target]

    def test_fallback_never_shorter_than_min_chars(self):
        text = "y " * (MIN_CHARS_TO_COMPRESS + 10)
        with patch("utils.content.pruner.prune_text", side_effect=Exception("fail")):
            result = compress_text(text, rate=0.01)  # extremely aggressive rate
        assert len(result) >= MIN_CHARS_TO_COMPRESS

    def test_fallback_respects_rate(self):
        text = "z " * 5000  # 10_000 chars
        rate = 0.3
        with patch("utils.content.pruner.prune_text", side_effect=Exception("fail")):
            result = compress_text(text, rate=rate)
        expected_len = max(MIN_CHARS_TO_COMPRESS, int(len(text) * rate))
        assert len(result) == expected_len
