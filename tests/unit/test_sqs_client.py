"""Unit tests for utils/sqs_client.py."""

import json
from unittest.mock import MagicMock, patch

import pytest

import utils.sqs_client as sqs_module
from utils.sqs_client import enqueue_pipeline_failure, enqueue_report


@pytest.fixture(autouse=True)
def reset_sqs_singleton():
    """Reset the module-level SQS client cache before each test."""
    original = sqs_module._sqs_client
    sqs_module._sqs_client = None
    yield
    sqs_module._sqs_client = original


# ---------------------------------------------------------------------------
# enqueue_report
# ---------------------------------------------------------------------------


class TestEnqueueReport:
    def test_returns_false_when_queue_url_not_set(self, monkeypatch):
        monkeypatch.delenv("SQS_QUEUE_URL", raising=False)
        assert enqueue_report("toronto", 42) is False

    def test_returns_true_on_success(self, monkeypatch):
        monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
        mock_sqs = MagicMock()
        with patch("utils.sqs_client.get_sqs_client", return_value=mock_sqs):
            result = enqueue_report("toronto", 42)
        assert result is True

    def test_calls_send_message_with_correct_body(self, monkeypatch):
        queue_url = "https://sqs.us-east-1.amazonaws.com/123/queue"
        monkeypatch.setenv("SQS_QUEUE_URL", queue_url)
        mock_sqs = MagicMock()
        with patch("utils.sqs_client.get_sqs_client", return_value=mock_sqs):
            enqueue_report("toronto", 42)
        mock_sqs.send_message.assert_called_once()
        call_kwargs = mock_sqs.send_message.call_args.kwargs
        assert call_kwargs["QueueUrl"] == queue_url
        body = json.loads(call_kwargs["MessageBody"])
        assert body == {"region": "toronto", "report_id": 42}

    def test_returns_false_on_boto3_exception(self, monkeypatch):
        monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/queue")
        mock_sqs = MagicMock()
        mock_sqs.send_message.side_effect = Exception("network error")
        with patch("utils.sqs_client.get_sqs_client", return_value=mock_sqs):
            result = enqueue_report("toronto", 42)
        assert result is False


# ---------------------------------------------------------------------------
# enqueue_pipeline_failure
# ---------------------------------------------------------------------------


class TestEnqueuePipelineFailure:
    def test_returns_false_when_dlq_url_not_set(self, monkeypatch):
        monkeypatch.delenv("SQS_PIPELINE_DLQ_URL", raising=False)
        assert enqueue_pipeline_failure("toronto", ["toronto (housing)"], None) is False

    def test_returns_true_on_success(self, monkeypatch):
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123/dlq")
        mock_sqs = MagicMock()
        with patch("utils.sqs_client.get_sqs_client", return_value=mock_sqs):
            result = enqueue_pipeline_failure("toronto", ["toronto (housing)"], 99)
        assert result is True

    def test_message_body_contains_required_fields(self, monkeypatch):
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123/dlq")
        mock_sqs = MagicMock()
        with patch("utils.sqs_client.get_sqs_client", return_value=mock_sqs):
            enqueue_pipeline_failure("toronto", ["toronto (housing)"], 99)
        body = json.loads(mock_sqs.send_message.call_args.kwargs["MessageBody"])
        assert body["region"] == "toronto"
        assert body["failures"] == ["toronto (housing)"]
        assert body["report_id"] == 99
        assert "timestamp" in body

    def test_report_id_none_is_included(self, monkeypatch):
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123/dlq")
        mock_sqs = MagicMock()
        with patch("utils.sqs_client.get_sqs_client", return_value=mock_sqs):
            enqueue_pipeline_failure("toronto", [], None)
        body = json.loads(mock_sqs.send_message.call_args.kwargs["MessageBody"])
        assert body["report_id"] is None

    def test_returns_false_on_boto3_exception(self, monkeypatch):
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123/dlq")
        mock_sqs = MagicMock()
        mock_sqs.send_message.side_effect = RuntimeError("timeout")
        with patch("utils.sqs_client.get_sqs_client", return_value=mock_sqs):
            result = enqueue_pipeline_failure("toronto", ["step"], None)
        assert result is False
