"""SQS client utilities for NV Local pipeline.

Provides functions to enqueue report-ready messages (main queue) and
pipeline failure metadata (dead letter queue) to Amazon SQS.
"""

import json
import os
from datetime import UTC, datetime

import boto3
from dotenv import load_dotenv

from utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

_sqs_client = None


def get_sqs_client():
    """Return a cached boto3 SQS client, creating one on first call.

    Credentials are discovered automatically from the environment
    (IAM role in Fargate, env vars or ~/.aws locally).

    Returns:
        boto3 SQS client.
    """
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs")
    return _sqs_client


def enqueue_report(region: str, report_id: int) -> bool:
    """Enqueue a report-ready message for the Email Lambda.

    Args:
        region: Region name matching regions.region.
        report_id: The reports.id primary key returned by save_report().

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    queue_url = os.getenv("SQS_QUEUE_URL")
    if not queue_url:
        logger.error("SQS_QUEUE_URL not set — cannot enqueue report")
        return False

    try:
        sqs = get_sqs_client()
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps({"region": region, "report_id": report_id}),
        )
        logger.info(f"Enqueued SQS message: region={region}, report_id={report_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to enqueue SQS message: {e}")
        return False


def enqueue_pipeline_failure(
    region: str, failures: list[str], report_id: int | None
) -> bool:
    """Send pipeline failure metadata to the dead letter queue.

    Best-effort: catches all exceptions and returns False rather than
    raising, so a DLQ failure never masks the original pipeline error.

    Args:
        region: Region name that was being processed.
        failures: Labels of failed topics/steps (e.g. ["toronto (housing)"]).
        report_id: The report ID if any topic saved, or None if all failed.

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    dlq_url = os.getenv("SQS_PIPELINE_DLQ_URL")
    if not dlq_url:
        logger.error("SQS_PIPELINE_DLQ_URL not set — cannot enqueue failure metadata")
        return False

    try:
        sqs = get_sqs_client()
        sqs.send_message(
            QueueUrl=dlq_url,
            MessageBody=json.dumps(
                {
                    "region": region,
                    "failures": failures,
                    "report_id": report_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ),
        )
        logger.info(f"Enqueued pipeline failure to DLQ: region={region}")
        return True
    except Exception as e:
        logger.error(f"Failed to enqueue pipeline failure to DLQ: {e}")
        return False
