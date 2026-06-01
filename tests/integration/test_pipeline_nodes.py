"""Integration tests for the note_taker → summary_writer node sequence.

Each test mocks only the LLM calls (OpenAI) and verifies that ChainData
flows correctly through the composed node chain.
"""

from unittest.mock import MagicMock, patch

from utils.schemas.pydantic import LegislationItem, WriterOutput

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(text: str):
    response = MagicMock()
    response.content = text
    return response


def _writer_output():
    return WriterOutput(
        items=[
            LegislationItem(
                header="Council passes housing bill",
                bullets=["Requires justification for evictions."],
                cited_sources=[1],
            )
        ]
    )


def _base_chain_data(region="toronto", topics=None):
    topics = topics or ["housing"]
    return {
        "region": region,
        "topic_results": {
            t: {
                "topic_description": f"{t} policy",
                "legislation_sources": ["https://toronto.ca/council"],
                "legislation_content": ["Detailed content about legislative bill."],
                "findings": ["https://toronto.ca/council"],
                "overview": f"Overview of {t} for {region}.",
            }
            for t in topics
        },
    }


# ---------------------------------------------------------------------------
# note_taker node
# ---------------------------------------------------------------------------


class TestNoteTakerNode:
    def _invoke_note_taker(self, chain_data, note_text="Generated research notes."):
        from pipelines.node.note_taker import _get_model, note_taker_chain

        _get_model.cache_clear()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = _make_llm_response(note_text)
        with patch("pipelines.node.note_taker.get_llm", return_value=mock_llm):
            _get_model.cache_clear()
            return note_taker_chain.invoke(chain_data)

    def test_adds_notes_to_each_topic(self):
        data = _base_chain_data(topics=["housing", "transit"])
        result = self._invoke_note_taker(data)
        assert "notes" in result["topic_results"]["housing"]
        assert "notes" in result["topic_results"]["transit"]

    def test_note_content_matches_llm_output(self):
        data = _base_chain_data()
        result = self._invoke_note_taker(data, note_text="Notes: Bill A passed 7-2.")
        assert result["topic_results"]["housing"]["notes"] == "Notes: Bill A passed 7-2."

    def test_preserves_existing_topic_fields(self):
        data = _base_chain_data()
        result = self._invoke_note_taker(data)
        topic = result["topic_results"]["housing"]
        assert "legislation_sources" in topic
        assert "legislation_content" in topic

    def test_region_preserved(self):
        data = _base_chain_data(region="ottawa")
        result = self._invoke_note_taker(data)
        assert result["region"] == "ottawa"


# ---------------------------------------------------------------------------
# summary_writer node
# ---------------------------------------------------------------------------


class TestSummaryWriterNode:
    def _invoke_summary_writer(self, chain_data, writer_output=None):
        from pipelines.node.summary_writer import _get_model, summary_writer_chain

        if writer_output is None:
            writer_output = _writer_output()

        _get_model.cache_clear()
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = writer_output
        with patch("pipelines.node.summary_writer.get_structured_llm", return_value=mock_llm):
            _get_model.cache_clear()
            return summary_writer_chain.invoke(chain_data)

    def test_adds_legislation_summary_to_topic(self):
        data = _base_chain_data()
        data["topic_results"]["housing"]["notes"] = "Research notes."
        result = self._invoke_summary_writer(data)
        assert "legislation_summary" in result["topic_results"]["housing"]

    def test_summary_is_writer_output_instance(self):
        data = _base_chain_data()
        data["topic_results"]["housing"]["notes"] = "notes"
        expected = _writer_output()
        result = self._invoke_summary_writer(data, writer_output=expected)
        assert result["topic_results"]["housing"]["legislation_summary"] is expected

    def test_empty_writer_output_sets_none(self):
        data = _base_chain_data()
        data["topic_results"]["housing"]["notes"] = "notes"
        result = self._invoke_summary_writer(data, writer_output=WriterOutput(items=[]))
        assert result["topic_results"]["housing"]["legislation_summary"] is None

    def test_region_preserved(self):
        data = _base_chain_data(region="san-diego")
        data["topic_results"]["housing"]["notes"] = "notes"
        result = self._invoke_summary_writer(data)
        assert result["region"] == "san-diego"


# ---------------------------------------------------------------------------
# note_taker → summary_writer composed chain
# ---------------------------------------------------------------------------


class TestNoteTakerToSummaryWriterChain:
    def test_full_chain_produces_legislation_summary(self):
        """Data produced by note_taker flows cleanly into summary_writer."""
        data = _base_chain_data()
        note_text = "Council passed good cause eviction ordinance 7-2."
        expected_summary = _writer_output()

        mock_note_llm = MagicMock()
        mock_note_llm.invoke.return_value = _make_llm_response(note_text)

        mock_writer_llm = MagicMock()
        mock_writer_llm.invoke.return_value = expected_summary

        from pipelines.node.note_taker import _get_model as nt_get_model
        from pipelines.node.note_taker import note_taker_chain
        from pipelines.node.summary_writer import _get_model as sw_get_model
        from pipelines.node.summary_writer import summary_writer_chain

        nt_get_model.cache_clear()
        sw_get_model.cache_clear()

        with (
            patch("pipelines.node.note_taker.get_llm", return_value=mock_note_llm),
            patch(
                "pipelines.node.summary_writer.get_structured_llm",
                return_value=mock_writer_llm,
            ),
        ):
            nt_get_model.cache_clear()
            sw_get_model.cache_clear()
            after_notes = note_taker_chain.invoke(data)
            final = summary_writer_chain.invoke(after_notes)

        topic = final["topic_results"]["housing"]
        assert topic["notes"] == note_text
        assert topic["legislation_summary"] is expected_summary
        assert topic["legislation_summary"].items[0].header == "Council passes housing bill"

    def test_full_chain_no_content_produces_no_summary(self):
        """Topics with no content should end with notes=placeholder and summary=None."""
        data = {
            "region": "toronto",
            "topic_results": {
                "housing": {
                    "topic_description": "Housing",
                    "legislation_sources": [],
                    "legislation_content": [],  # no content
                }
            },
        }

        from pipelines.node.note_taker import _get_model as nt_get_model
        from pipelines.node.note_taker import note_taker_chain
        from pipelines.node.summary_writer import _get_model as sw_get_model
        from pipelines.node.summary_writer import summary_writer_chain

        nt_get_model.cache_clear()
        sw_get_model.cache_clear()

        mock_writer_llm = MagicMock()
        mock_writer_llm.invoke.return_value = WriterOutput(items=[])

        with patch(
            "pipelines.node.summary_writer.get_structured_llm",
            return_value=mock_writer_llm,
        ):
            sw_get_model.cache_clear()
            after_notes = note_taker_chain.invoke(data)
            final = summary_writer_chain.invoke(after_notes)

        topic = final["topic_results"]["housing"]
        assert topic["notes"] == "No legislation content found."
        assert topic["legislation_summary"] is None
