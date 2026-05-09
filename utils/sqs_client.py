"""SQS client utilities for NV Local pipeline.

Provides functions to enqueue report-ready messages (main queue) and
pipeline failure metadata (dead letter queue) to Amazon SQS.
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_sqs_client():
    """Create and return a boto3 SQS client.

    Credentials are discovered automatically from the environment
    (IAM role in Fargate, env vars or ~/.aws locally).

    Returns:
        boto3 SQS client.
    """
    return boto3.client("sqs")


def enqueue_report(city: str, report_id: int) -> bool:
    """Enqueue a report-ready message for the Email Lambda.

    Args:
        city: City name matching supported_cities.city.
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
            MessageBody=json.dumps({"city": city, "report_id": report_id}),
        )
        logger.info(f"Enqueued SQS message: city={city}, report_id={report_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to enqueue SQS message: {e}")
        return False


def enqueue_pipeline_failure(
    city: str, failures: list[str], report_id: int | None
) -> bool:
    """Send pipeline failure metadata to the dead letter queue.

    Best-effort: catches all exceptions and returns False rather than
    raising, so a DLQ failure never masks the original pipeline error.

    Args:
        city: City name that was being processed.
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
            MessageBody=json.dumps({
                "city": city,
                "failures": failures,
                "report_id": report_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        )
        logger.info(f"Enqueued pipeline failure to DLQ: city={city}")
        return True
    except Exception as e:
        logger.error(f"Failed to enqueue pipeline failure to DLQ: {e}")
        return False
