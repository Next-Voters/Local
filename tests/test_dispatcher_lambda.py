"""Dispatcher Lambda integration tests.

Fetches dispatcher.py from the aws-lambda-scripts repo at test time,
patches Supabase and stubs ECS run_task, then verifies fan-out logic.
"""

import importlib
import json
import sys
import types
from unittest.mock import MagicMock, patch

import httpx
import pytest

DISPATCHER_URL = (
    "https://raw.githubusercontent.com/"
    "next-voters/aws-lambda-scripts/main/dispatcher.py"
)

REQUIRED_ENV = {
    "SUPABASE_URL": "http://fake-supabase.local",
    "SUPABASE_KEY": "fake-key",
    "ECS_CLUSTER": "test-cluster",
    "ECS_TASK_DEFINITION": "test-task-def",
    "SUBNETS": "subnet-aaa,subnet-bbb",
    "SECURITY_GROUPS": "sg-111",
    "CONTAINER_NAME": "nv-local",
}


@pytest.fixture(scope="module")
def dispatcher_source():
    """Fetch the dispatcher Lambda source code from GitHub."""
    resp = httpx.get(DISPATCHER_URL, timeout=15)
    resp.raise_for_status()
    return resp.text


def _load_dispatcher(source: str, mock_ecs_client, mock_fetch_regions):
    """Dynamically load the dispatcher module with mocked dependencies.

    Sets required env vars, stubs boto3.client('ecs') and the Supabase
    fetch_regions call, then exec's the source into a fresh module.
    """
    import os

    for k, v in REQUIRED_ENV.items():
        os.environ.setdefault(k, v)

    module = types.ModuleType("dispatcher")
    module.__dict__["__name__"] = "dispatcher"

    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_ecs_client

    mock_supabase_mod = MagicMock()
    mock_supabase_client = MagicMock()
    mock_supabase_mod.create_client.return_value = mock_supabase_client

    table_mock = MagicMock()
    mock_supabase_client.table.return_value = table_mock
    select_mock = MagicMock()
    table_mock.select.return_value = select_mock
    execute_mock = MagicMock()
    select_mock.execute.return_value = execute_mock
    execute_mock.data = [{"region": r} for r in mock_fetch_regions]

    saved_modules = {}
    for mod_name, mod_obj in [("boto3", mock_boto3), ("supabase", mock_supabase_mod)]:
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mod_obj

    try:
        exec(compile(source, "dispatcher.py", "exec"), module.__dict__)
    finally:
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig

    return module


class TestDispatcherFanOut:
    """Dispatcher fans out one ECS task per region."""

    def test_fans_out_per_region(self, dispatcher_source, monkeypatch):
        """run_task called once per region with correct REGION override."""
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        regions = ["toronto", "vancouver"]
        mock_ecs = MagicMock()
        mock_ecs.run_task.return_value = {
            "tasks": [{"taskArn": "arn:aws:ecs:us-east-1:123:task/abc"}],
            "failures": [],
        }

        module = _load_dispatcher(dispatcher_source, mock_ecs, regions)
        result = module.lambda_handler({}, None)

        assert mock_ecs.run_task.call_count == len(regions)

        for i, region in enumerate(regions):
            call_kwargs = mock_ecs.run_task.call_args_list[i][1]
            overrides = call_kwargs["overrides"]["containerOverrides"][0]
            env_list = overrides["environment"]
            region_env = next(e for e in env_list if e["name"] == "REGION")
            assert region_env["value"] == region

        body = json.loads(result["body"])
        assert body["dispatched"] == 2
        assert body["failed"] == 0
        assert result["statusCode"] == 200

    def test_handles_ecs_failure(self, dispatcher_source, monkeypatch):
        """ECS failure populates the failures list."""
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_ecs = MagicMock()
        mock_ecs.run_task.side_effect = RuntimeError("Capacity limit reached")

        module = _load_dispatcher(dispatcher_source, mock_ecs, ["test-city"])
        result = module.lambda_handler({}, None)

        body = json.loads(result["body"])
        assert body["failed"] == 1
        assert body["dispatched"] == 0
        assert result["statusCode"] == 207
        assert "Capacity limit reached" in body["failures"][0]["error"]

    def test_network_configuration(self, dispatcher_source, monkeypatch):
        """run_task includes correct networkConfiguration."""
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_ecs = MagicMock()
        mock_ecs.run_task.return_value = {
            "tasks": [{"taskArn": "arn:aws:ecs:us-east-1:123:task/xyz"}],
            "failures": [],
        }

        module = _load_dispatcher(dispatcher_source, mock_ecs, ["test-city"])
        module.lambda_handler({}, None)

        call_kwargs = mock_ecs.run_task.call_args[1]
        vpc_config = call_kwargs["networkConfiguration"]["awsvpcConfiguration"]
        assert vpc_config["subnets"] == ["subnet-aaa", "subnet-bbb"]
        assert vpc_config["securityGroups"] == ["sg-111"]
        assert vpc_config["assignPublicIp"] == "ENABLED"
