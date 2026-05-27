"""Shared pytest fixtures for LocalStack integration tests."""

import os

import boto3
import pytest

from tests.localstack_setup import create_sqs_queues

LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")


@pytest.fixture(scope="session")
def localstack_endpoint():
    """Return the LocalStack endpoint URL."""
    return LOCALSTACK_ENDPOINT


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    """Set dummy AWS credentials so boto3 talks to LocalStack."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture()
def sqs_queues(localstack_endpoint):
    """Create the three SQS queues in LocalStack, yield URLs, then purge."""
    urls = create_sqs_queues(localstack_endpoint)
    yield urls

    sqs = boto3.client(
        "sqs", endpoint_url=localstack_endpoint, region_name="us-east-1"
    )
    for url in urls.values():
        try:
            sqs.purge_queue(QueueUrl=url)
        except Exception:
            pass


@pytest.fixture()
def localstack_sqs_client(localstack_endpoint):
    """Return a boto3 SQS client pointed at LocalStack."""
    return boto3.client(
        "sqs", endpoint_url=localstack_endpoint, region_name="us-east-1"
    )


@pytest.fixture()
def patch_sqs_client(localstack_sqs_client, monkeypatch):
    """Patch get_sqs_client() to return the LocalStack-pointed client.

    Also resets the module-level _sqs_client cache after the test to
    prevent cross-test leakage.
    """
    import utils.sqs_client as sqs_mod

    monkeypatch.setattr(sqs_mod, "get_sqs_client", lambda: localstack_sqs_client)
    monkeypatch.setattr(sqs_mod, "_sqs_client", None)

    yield localstack_sqs_client

    sqs_mod._sqs_client = None


@pytest.fixture()
def mock_supabase(monkeypatch):
    """Patch Supabase calls to return canned region/topic data."""
    import utils.supabase_client as sb_mod

    monkeypatch.setattr(
        sb_mod,
        "get_supported_regions_from_db",
        lambda: ["test-city"],
    )

    monkeypatch.setattr(
        sb_mod,
        "get_supported_topics",
        lambda: [{"topic_name": "housing", "description": "Housing policy"}],
    )
