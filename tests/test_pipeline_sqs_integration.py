"""Container-mode end-to-end integration tests.

Verifies that run_container_mode() correctly enqueues messages to SQS
(report-ready or pipeline DLQ) when the pipeline + Supabase are mocked.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from utils.schemas.pydantic import LegislationItem, WriterOutput


def _canned_pipeline_result():
    """Return a pipeline result dict with a valid WriterOutput."""
    writer_output = WriterOutput(
        items=[
            LegislationItem(
                header="Council passes rent stabilization",
                bullets=["Caps annual increases at 3%", "Applies to buildings with 6+ units"],
                cited_sources=[1],
            )
        ]
    )
    return {
        "topic_results": {
            "housing": {
                "legislation_summary": writer_output,
                "legislation_sources": [
                    {"url": "https://example.gov/rent-bill", "content": "..."}
                ],
            }
        }
    }


class TestContainerModeSQS:
    """run_container_mode() SQS integration with LocalStack."""

    def test_enqueues_report_on_success(
        self, sqs_queues, patch_sqs_client, monkeypatch
    ):
        """Successful pipeline run enqueues {region, report_id} to report-ready queue."""
        monkeypatch.setenv("SQS_QUEUE_URL", sqs_queues["report_ready"])
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", sqs_queues["pipeline_dlq"])

        with (
            patch(
                "utils.supabase_client.get_supported_regions_from_db",
                return_value=["test-city"],
            ),
            patch(
                "pipelines.nv_local.chain"
            ) as mock_chain,
            patch(
                "utils.report.storage.save_report", return_value=42
            ),
        ):
            mock_chain.invoke.return_value = _canned_pipeline_result()

            from main import run_container_mode

            exit_code = run_container_mode("test-city")

        assert exit_code == 0

        resp = patch_sqs_client.receive_message(
            QueueUrl=sqs_queues["report_ready"],
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
        )
        messages = resp.get("Messages", [])
        assert len(messages) == 1

        body = json.loads(messages[0]["Body"])
        assert body == {"region": "test-city", "report_id": 42}

    def test_enqueues_failure_on_save_error(
        self, sqs_queues, patch_sqs_client, monkeypatch
    ):
        """save_report() returning None triggers DLQ message."""
        monkeypatch.setenv("SQS_QUEUE_URL", sqs_queues["report_ready"])
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", sqs_queues["pipeline_dlq"])

        with (
            patch(
                "utils.supabase_client.get_supported_regions_from_db",
                return_value=["test-city"],
            ),
            patch(
                "pipelines.nv_local.chain"
            ) as mock_chain,
            patch(
                "utils.report.storage.save_report", return_value=None
            ),
        ):
            mock_chain.invoke.return_value = _canned_pipeline_result()

            from main import run_container_mode

            exit_code = run_container_mode("test-city")

        assert exit_code == 1

        resp = patch_sqs_client.receive_message(
            QueueUrl=sqs_queues["pipeline_dlq"],
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
        )
        messages = resp.get("Messages", [])
        assert len(messages) == 1

        body = json.loads(messages[0]["Body"])
        assert body["region"] == "test-city"
        assert any("housing" in f for f in body["failures"])

    def test_invalid_region_returns_1(
        self, sqs_queues, patch_sqs_client, monkeypatch
    ):
        """Invalid region returns exit code 1 without touching SQS."""
        monkeypatch.setenv("SQS_QUEUE_URL", sqs_queues["report_ready"])
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", sqs_queues["pipeline_dlq"])

        with patch(
            "utils.supabase_client.get_supported_regions_from_db",
            return_value=["test-city"],
        ):
            from main import run_container_mode

            exit_code = run_container_mode("nonexistent-city")

        assert exit_code == 1

        for queue_url in sqs_queues.values():
            resp = patch_sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=1,
            )
            assert resp.get("Messages", []) == []

    def test_pipeline_exception_enqueues_failure(
        self, sqs_queues, patch_sqs_client, monkeypatch
    ):
        """Pipeline invocation exception triggers DLQ message."""
        monkeypatch.setenv("SQS_QUEUE_URL", sqs_queues["report_ready"])
        monkeypatch.setenv("SQS_PIPELINE_DLQ_URL", sqs_queues["pipeline_dlq"])

        with (
            patch(
                "utils.supabase_client.get_supported_regions_from_db",
                return_value=["test-city"],
            ),
            patch(
                "pipelines.nv_local.chain"
            ) as mock_chain,
        ):
            mock_chain.invoke.side_effect = RuntimeError("LLM timeout")

            from main import run_container_mode

            exit_code = run_container_mode("test-city")

        assert exit_code == 1

        resp = patch_sqs_client.receive_message(
            QueueUrl=sqs_queues["pipeline_dlq"],
            MaxNumberOfMessages=1,
            WaitTimeSeconds=5,
        )
        messages = resp.get("Messages", [])
        assert len(messages) == 1

        body = json.loads(messages[0]["Body"])
        assert body["region"] == "test-city"
        assert "pipeline invocation" in body["failures"][0]
