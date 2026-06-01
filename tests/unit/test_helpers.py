"""Unit tests for tools/_helpers.py.

Pure function tests — no mocking required.
"""

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from tools._helpers import err, ok


class TestOk:
    def test_returns_command(self):
        result = ok("call-1")
        assert isinstance(result, Command)

    def test_update_contains_messages(self):
        result = ok("call-1", "success")
        assert "messages" in result.update

    def test_message_is_tool_message(self):
        result = ok("call-1", "done")
        msgs = result.update["messages"]
        assert len(msgs) == 1
        assert isinstance(msgs[0], ToolMessage)

    def test_message_content(self):
        result = ok("call-1", "everything went fine")
        assert result.update["messages"][0].content == "everything went fine"

    def test_message_tool_call_id(self):
        result = ok("my-tool-id", "ok")
        assert result.update["messages"][0].tool_call_id == "my-tool-id"

    def test_empty_message(self):
        result = ok("call-1")
        assert result.update["messages"][0].content == ""

    def test_state_updates_included(self):
        result = ok("call-1", "ok", research_summary="summary text", notes="some notes")
        assert result.update["research_summary"] == "summary text"
        assert result.update["notes"] == "some notes"

    def test_state_updates_do_not_overwrite_messages(self):
        result = ok("call-1", "msg", custom_field="value")
        assert "messages" in result.update
        assert result.update["custom_field"] == "value"


class TestErr:
    def test_returns_command(self):
        result = err("call-1", "something went wrong")
        assert isinstance(result, Command)

    def test_update_contains_only_messages(self):
        result = err("call-1", "failure")
        assert set(result.update.keys()) == {"messages"}

    def test_message_is_tool_message(self):
        result = err("call-1", "bad input")
        msgs = result.update["messages"]
        assert len(msgs) == 1
        assert isinstance(msgs[0], ToolMessage)

    def test_message_content(self):
        result = err("call-1", "Tavily API key not configured")
        assert result.update["messages"][0].content == "Tavily API key not configured"

    def test_message_tool_call_id(self):
        result = err("err-tool-id", "error")
        assert result.update["messages"][0].tool_call_id == "err-tool-id"

    def test_no_extra_state_mutations(self):
        result = err("call-1", "error msg")
        assert "legislation_sources" not in result.update
        assert "research_summary" not in result.update
