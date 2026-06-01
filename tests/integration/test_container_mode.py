"""Integration tests for main.run_container_mode.

All external I/O (Supabase, pipeline chain, SQS) is mocked so the test
exercises the orchestration logic in run_container_mode without network calls.

Patch targets use the source-module paths, NOT "main.xyz", because every
dependency is imported INSIDE the function body (local imports) and therefore
never exists in main's module-level namespace.
"""

from unittest.mock import patch

from main import run_container_mode
from utils.schemas.pydantic import LegislationItem, WriterOutput

# ---------------------------------------------------------------------------
# Patch target constants — keeps the test bodies readable
# ---------------------------------------------------------------------------

_GET_REGIONS = "utils.supabase_client.get_supported_regions_from_db"
_CHAIN = "pipelines.nv_local.chain"
_SAVE_REPORT = "utils.report.storage.save_report"
_ENQUEUE_REPORT = "utils.sqs_client.enqueue_report"
_ENQUEUE_FAILURE = "utils.sqs_client.enqueue_pipeline_failure"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _writer_output_with_item():
    return WriterOutput(
        items=[LegislationItem(header="h", bullets=["b"], cited_sources=[])]
    )


def _chain_result(region="toronto", topics=("housing",)):
    """Build a synthetic chain.invoke() result."""
    return {
        "region": region,
        "topic_results": {
            t: {
                "topic_description": f"{t} policy",
                "legislation_sources": ["https://toronto.ca"],
                "legislation_content": ["content"],
                "notes": "notes",
                "legislation_summary": _writer_output_with_item(),
            }
            for t in topics
        },
    }


# ---------------------------------------------------------------------------
# Region validation
# ---------------------------------------------------------------------------


class TestRegionValidation:
    def test_invalid_region_returns_1(self):
        with patch(_GET_REGIONS, return_value=["toronto", "ottawa"]):
            result = run_container_mode("nonexistent-city")
        assert result == 1

    def test_supabase_error_returns_1(self):
        with patch(_GET_REGIONS, side_effect=Exception("DB down")):
            result = run_container_mode("toronto")
        assert result == 1


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


class TestPipelineExecution:
    def test_pipeline_failure_returns_1_and_enqueues_dlq(self):
        with (
            patch(_GET_REGIONS, return_value=["toronto"]),
            patch(_CHAIN) as mock_chain,
            patch(_ENQUEUE_FAILURE) as mock_dlq,
            patch(_ENQUEUE_REPORT),
            patch(_SAVE_REPORT),
        ):
            mock_chain.invoke.side_effect = RuntimeError("agent loop exploded")
            result = run_container_mode("toronto")

        assert result == 1
        mock_dlq.assert_called_once()
        assert mock_dlq.call_args.args[0] == "toronto"

    def test_successful_run_returns_0(self):
        chain_result = _chain_result()
        with (
            patch(_GET_REGIONS, return_value=["toronto"]),
            patch(_CHAIN) as mock_chain,
            patch(_SAVE_REPORT, return_value=42),
            patch(_ENQUEUE_REPORT, return_value=True),
            patch(_ENQUEUE_FAILURE) as mock_dlq,
        ):
            mock_chain.invoke.return_value = chain_result
            result = run_container_mode("toronto")

        assert result == 0
        mock_dlq.assert_not_called()


# ---------------------------------------------------------------------------
# Report saving
# ---------------------------------------------------------------------------


class TestReportSaving:
    def test_save_report_called_per_topic(self):
        chain_result = _chain_result(topics=("housing", "transit"))
        with (
            patch(_GET_REGIONS, return_value=["toronto"]),
            patch(_CHAIN) as mock_chain,
            patch(_SAVE_REPORT, return_value=10) as mock_save,
            patch(_ENQUEUE_REPORT, return_value=True),
            patch(_ENQUEUE_FAILURE),
        ):
            mock_chain.invoke.return_value = chain_result
            run_container_mode("toronto")

        assert mock_save.call_count == 2
        called_topics = {c.args[1] for c in mock_save.call_args_list}
        assert called_topics == {"housing", "transit"}

    def test_save_report_returns_none_is_treated_as_failure(self):
        chain_result = _chain_result()
        with (
            patch(_GET_REGIONS, return_value=["toronto"]),
            patch(_CHAIN) as mock_chain,
            patch(_SAVE_REPORT, return_value=None),
            patch(_ENQUEUE_REPORT, return_value=True),
            patch(_ENQUEUE_FAILURE) as mock_dlq,
        ):
            mock_chain.invoke.return_value = chain_result
            result = run_container_mode("toronto")

        assert result == 1
        mock_dlq.assert_called_once()

    def test_save_report_exception_treated_as_failure(self):
        chain_result = _chain_result()
        with (
            patch(_GET_REGIONS, return_value=["toronto"]),
            patch(_CHAIN) as mock_chain,
            patch(_SAVE_REPORT, side_effect=Exception("write failed")),
            patch(_ENQUEUE_REPORT, return_value=True),
            patch(_ENQUEUE_FAILURE) as mock_dlq,
        ):
            mock_chain.invoke.return_value = chain_result
            result = run_container_mode("toronto")

        assert result == 1
        mock_dlq.assert_called_once()


# ---------------------------------------------------------------------------
# SQS notification
# ---------------------------------------------------------------------------


class TestSqsNotification:
    def test_enqueue_report_called_with_report_id(self):
        chain_result = _chain_result()
        with (
            patch(_GET_REGIONS, return_value=["toronto"]),
            patch(_CHAIN) as mock_chain,
            patch(_SAVE_REPORT, return_value=77),
            patch(_ENQUEUE_REPORT, return_value=True) as mock_enqueue,
            patch(_ENQUEUE_FAILURE),
        ):
            mock_chain.invoke.return_value = chain_result
            run_container_mode("toronto")

        mock_enqueue.assert_called_once_with("toronto", 77)

    def test_sqs_failure_adds_to_failures_and_returns_1(self):
        chain_result = _chain_result()
        with (
            patch(_GET_REGIONS, return_value=["toronto"]),
            patch(_CHAIN) as mock_chain,
            patch(_SAVE_REPORT, return_value=77),
            patch(_ENQUEUE_REPORT, return_value=False),
            patch(_ENQUEUE_FAILURE) as mock_dlq,
        ):
            mock_chain.invoke.return_value = chain_result
            result = run_container_mode("toronto")

        assert result == 1
        mock_dlq.assert_called_once()
        failures_arg = mock_dlq.call_args.args[1]
        assert any("SQS" in f for f in failures_arg)

    def test_no_report_id_skips_enqueue_report(self):
        """If all topics failed to save, enqueue_report should never be called."""
        chain_result = _chain_result()
        with (
            patch(_GET_REGIONS, return_value=["toronto"]),
            patch(_CHAIN) as mock_chain,
            patch(_SAVE_REPORT, return_value=None),
            patch(_ENQUEUE_REPORT) as mock_enqueue,
            patch(_ENQUEUE_FAILURE),
        ):
            mock_chain.invoke.return_value = chain_result
            run_container_mode("toronto")

        mock_enqueue.assert_not_called()
