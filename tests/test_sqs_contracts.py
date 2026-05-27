"""Tests for SQS message format contracts.

Verifies that enqueue_report() and enqueue_pipeline_failure() produce
correctly-shaped messages on the right queues in LocalStack.
"""

import json

import pytest


class TestEnqueueReport:
    """enqueue_report() message format and error handling."""

    def test_message_format(self, sqs_queues, patch_sqs_client, monkeypatch):
        """Message body has {region: str, report_id: int}."""
        monkeypatch.setenv("SQS_QUEUE_URL", sqs_queues["report_ready"])

        from utils.sqs_client import enqueue_report

        result = enqueue_report("test-city", 42)
        assert result is True

        resp = patch_sqs_client.receive_message(
            QueueUrl=sqs_queues["report_ready"],
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
        )
        messages = resp.get("Messages", [])
        assert len(messages) == 1

        body = json.loads(messages[0]["Body"])
        assert body == {"region": "test-city", "report_id": 42}

    def test_missing_queue_url(self, sqs_queues, patch_sqs_client, monkeypatch):
        """Returns False when SQS_QUEUE_URL is not set."""
        monkeypatch.delenv("SQS_QUEUE_URL", raising=False)

        from utils.sqs_client import enqueue_report

        result = enqueue_report("test-city", 1)
        assert result is False

    def test_message_arrives_on_correct_queue(
        self, sqs_queues, patch_sqs_client, monkeypatch
    ):
        """Message lands on report-ready queue, not the DLQ."""
        monkeypatch.setenv("SQS_QUEUE_URL", sqs_queues["report_ready"])

        from utils.sqs_client import enqueue_report

        enqueue_report("test-city", 99)

        dlq_resp = patch_sqs_client.receive_message(
            QueueUrl=sqs_queues["pipeline_dlq"],
            MaxNumberOfMessages=1,
            WaitTimeSeconds=1,
        )
        assert dlq_resp.get("Messages", []) == []


class TestEnqueuePipelineFailure:
    """enqueue_pipeline_failure() message format and error handling."""

    def test_message_format(self, sqs_queues, patch_sqs_client, monkeypatch):
        """Message body has {region, failures, report_id, timestamp}."""
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", sqs_queues["pipeline_dlq"])

        from utils.sqs_client import enqueue_pipeline_failure

        result = enqueue_pipeline_failure(
            "test-city", ["test-city (housing)"], None
        )
        assert result is True

        resp = patch_sqs_client.receive_message(
            QueueUrl=sqs_queues["pipeline_dlq"],
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
        )
        messages = resp.get("Messages", [])
        assert len(messages) == 1

        body = json.loads(messages[0]["Body"])
        assert body["region"] == "test-city"
        assert body["failures"] == ["test-city (housing)"]
        assert body["report_id"] is None
        assert "timestamp" in body

    def test_with_partial_report_id(
        self, sqs_queues, patch_sqs_client, monkeypatch
    ):
        """report_id is included when some topics succeeded."""
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", sqs_queues["pipeline_dlq"])

        from utils.sqs_client import enqueue_pipeline_failure

        enqueue_pipeline_failure("test-city", ["test-city (education)"], 7)

        resp = patch_sqs_client.receive_message(
            QueueUrl=sqs_queues["pipeline_dlq"],
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
        )
        body = json.loads(resp["Messages"][0]["Body"])
        assert body["report_id"] == 7

    def test_missing_dlq_url(self, sqs_queues, patch_sqs_client, monkeypatch):
        """Returns False when SQS_PIPELINE_DLQ_URL is not set."""
        monkeypatch.delenv("SQS_PIPELINE_DLQ_URL", raising=False)

        from utils.sqs_client import enqueue_pipeline_failure

        result = enqueue_pipeline_failure("test-city", ["fail"], None)
        assert result is False
