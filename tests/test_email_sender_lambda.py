"""Email sender Lambda integration tests.

Fetches email_sender.py from the aws-lambda-scripts repo at test time,
patches Supabase and template loading, then verifies email dispatch logic.
"""

import json
import sys
import types
from datetime import date
from unittest.mock import MagicMock, mock_open, patch

import httpx
import pytest

EMAIL_SENDER_URL = (
    "https://raw.githubusercontent.com/"
    "next-voters/aws-lambda-scripts/main/email_sender.py"
)

REQUIRED_ENV = {
    "SUPABASE_URL": "http://fake-supabase.local",
    "SUPABASE_KEY": "fake-key",
    "SES_SENDER_EMAIL": "reports@test.nextvoters.com",
}

MINIMAL_TEMPLATE = """<html><body>
{{CITY_HEADER}}
{{HEADER_DATE}}
{{TABLE_OF_CONTENTS}}
{{TOPIC_SECTIONS}}
{{CONTENT}}
{{CITATIONS}}
<a href="{{TWITTER_SHARE_URL}}">Twitter</a>
<a href="{{FACEBOOK_SHARE_URL}}">Facebook</a>
<a href="{{LINKEDIN_SHARE_URL}}">LinkedIn</a>
<a href="{{UNSUBSCRIBE_URL}}">Unsubscribe</a> from this list.
</body></html>"""


@pytest.fixture(scope="module")
def email_sender_source():
    """Fetch the email sender Lambda source code from GitHub."""
    resp = httpx.get(EMAIL_SENDER_URL, timeout=15)
    resp.raise_for_status()
    return resp.text


def _canned_subscribers():
    return [
        {
            "contact": "user@example.com",
            "subscription_regions": {
                "city": "test-city",
                "region": None,
                "country": None,
            },
            "subscription_topics": [
                {
                    "topic_id": 1,
                    "supported_topics": {"topic_name": "housing"},
                }
            ],
        }
    ]


def _canned_report_headers():
    return [
        {
            "topic_id": 1,
            "header": "Council passes rent cap",
            "bullets": ["Caps increases at 3%"],
            "sources": ["https://example.gov/rent"],
            "reports": {
                "region": "test-city",
                "report_date": date.today().isoformat(),
            },
        }
    ]


def _load_email_sender(source: str, mock_ses_client, subscribers_data, reports_data):
    """Dynamically load the email_sender module with mocked dependencies.

    Patches: boto3, supabase, and the template file open().
    """
    import os

    for k, v in REQUIRED_ENV.items():
        os.environ.setdefault(k, v)

    module = types.ModuleType("email_sender")
    module.__dict__["__name__"] = "email_sender"

    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_ses_client

    mock_supabase_mod = MagicMock()
    mock_supabase_client_instance = MagicMock()
    mock_supabase_mod.create_client.return_value = mock_supabase_client_instance

    table_mock = MagicMock()
    mock_supabase_client_instance.table.return_value = table_mock

    def _make_chain(data):
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.range.return_value = chain
        execute_result = MagicMock()
        execute_result.data = data
        chain.execute.return_value = execute_result
        return chain

    sub_chain = _make_chain(subscribers_data)
    report_chain = _make_chain(reports_data)

    call_count = {"n": 0}
    original_table = table_mock

    def table_side_effect(name):
        call_count["n"] += 1
        if name == "subscriptions":
            return sub_chain
        elif name == "report_headers":
            return report_chain
        return MagicMock()

    table_mock.side_effect = table_side_effect
    mock_supabase_client_instance.table = table_mock

    saved_modules = {}
    for mod_name, mod_obj in [("boto3", mock_boto3), ("supabase", mock_supabase_mod)]:
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mod_obj

    import builtins

    original_open = builtins.open

    def patched_open(path, *args, **kwargs):
        if isinstance(path, str) and "email_report.html" in path:
            from io import StringIO
            return StringIO(MINIMAL_TEMPLATE)
        return original_open(path, *args, **kwargs)

    builtins.open = patched_open

    try:
        exec(compile(source, "email_sender.py", "exec"), module.__dict__)
    finally:
        builtins.open = original_open
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig

    return module


class TestEmailSenderProcessing:
    """Email sender Lambda processes SQS events and calls SES."""

    def test_processes_subscribers_and_sends_email(
        self, email_sender_source, monkeypatch
    ):
        """Handler fetches subscribers + reports, calls SES send_bulk_email."""
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_ses = MagicMock()
        mock_ses.send_bulk_email.return_value = {
            "BulkEmailEntryResults": [{"Status": "SUCCESS"}]
        }

        module = _load_email_sender(
            email_sender_source,
            mock_ses,
            _canned_subscribers(),
            _canned_report_headers(),
        )

        result = module.lambda_handler({}, None)

        assert mock_ses.send_bulk_email.called
        body = json.loads(result["body"])
        assert body["sent"] >= 1
        assert result["statusCode"] == 200

    def test_no_reports_today_skips_send(self, email_sender_source, monkeypatch):
        """Empty reports cache → early return, no SES calls."""
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_ses = MagicMock()

        module = _load_email_sender(
            email_sender_source,
            mock_ses,
            _canned_subscribers(),
            [],
        )

        result = module.lambda_handler({}, None)

        assert not mock_ses.send_bulk_email.called
        body = json.loads(result["body"])
        assert body["sent"] == 0

    def test_ses_failure_returns_207(self, email_sender_source, monkeypatch):
        """SES send failure returns status 207 with failure details."""
        for k, v in REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_ses = MagicMock()
        mock_ses.send_bulk_email.return_value = {
            "BulkEmailEntryResults": [
                {"Status": "FAILED", "Error": "MessageRejected"}
            ]
        }

        module = _load_email_sender(
            email_sender_source,
            mock_ses,
            _canned_subscribers(),
            _canned_report_headers(),
        )

        result = module.lambda_handler({}, None)

        body = json.loads(result["body"])
        assert result["statusCode"] == 207
        assert body["failed"] >= 1
