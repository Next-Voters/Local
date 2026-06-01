"""Unit tests for pipelines/node/note_taker.py."""

from unittest.mock import MagicMock, patch



def _make_llm_response(text: str):
    """Build a mock LLM response with the given content string."""
    response = MagicMock()
    response.content = text
    return response


class TestResearchNoteTaker:
    def _run(self, inputs, llm_response_text="Generated notes."):
        """Helper: patch LLM and invoke research_note_taker."""
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(llm_response_text)

        # Clear lru_cache so the patched model is used
        from pipelines.node.note_taker import _get_model, research_note_taker

        _get_model.cache_clear()
        with patch("pipelines.node.note_taker.get_llm", return_value=mock_llm):
            _get_model.cache_clear()
            result = research_note_taker(inputs)
        return result

    def test_empty_topic_results_returned_unchanged(self):
        inputs = {"region": "toronto", "topic_results": {}}
        result = self._run(inputs)
        assert result["topic_results"] == {}

    def test_topic_with_no_content_gets_placeholder(self):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing policy",
                    "legislation_content": [],
                }
            },
        }
        result = self._run(inputs)
        assert result["topic_results"]["housing"]["notes"] == "No legislation content found."

    def test_topic_with_content_invokes_llm(self):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing policy",
                    "legislation_content": ["Page A content.", "Page B content."],
                }
            },
        }
        result = self._run(inputs, llm_response_text="Condensed notes about housing.")
        assert result["topic_results"]["housing"]["notes"] == "Condensed notes about housing."

    def test_other_topic_fields_preserved(self):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing policy",
                    "legislation_content": ["Some content."],
                    "legislation_sources": ["https://toronto.ca"],
                    "findings": ["https://toronto.ca"],
                }
            },
        }
        result = self._run(inputs)
        topic = result["topic_results"]["housing"]
        assert topic["legislation_sources"] == ["https://toronto.ca"]
        assert topic["findings"] == ["https://toronto.ca"]

    def test_multiple_topics_handled_independently(self):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_content": ["Content A"],
                },
                "transit": {
                    "topic_description": "Transit",
                    "legislation_content": [],
                },
            },
        }
        result = self._run(inputs, llm_response_text="Housing notes.")
        assert result["topic_results"]["housing"]["notes"] == "Housing notes."
        assert result["topic_results"]["transit"]["notes"] == "No legislation content found."

    def test_region_preserved_in_output(self):
        inputs = {"region": "san-francisco", "topic_results": {}}
        result = self._run(inputs)
        assert result["region"] == "san-francisco"

    def test_returns_new_dict_not_mutation(self):
        inputs = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_content": ["Content."],
                }
            },
        }
        result = self._run(inputs)
        assert result is not inputs
