"""Shared fixtures for the NV Local test suite."""

import pytest

from utils.schemas.pydantic import LegislationItem, WriterOutput


@pytest.fixture
def sample_legislation_item():
    """A single legislation item with two bullets and one source citation."""
    return LegislationItem(
        header="Council passes good cause eviction package",
        bullets=[
            "Requires landlords to provide written justification before evicting tenants.",
            "Takes effect January 1, 2025.",
        ],
        cited_sources=[1],
    )


@pytest.fixture
def sample_writer_output(sample_legislation_item):
    """WriterOutput with one legislation item."""
    return WriterOutput(items=[sample_legislation_item])


@pytest.fixture
def sample_chain_data(sample_writer_output):
    """Minimal ChainData with one topic fully populated through the pipeline."""
    return {
        "region": "toronto",
        "topic_results": {
            "housing": {
                "topic_description": "Municipal housing and rental policy",
                "legislation_sources": [
                    "https://toronto.ca/council/agenda/2024-11-01/",
                    {"url": "https://legistar.com/toronto/bills/12345", "content": "full text"},
                ],
                "legislation_content": [
                    "Compressed content about housing bill A.",
                    "Compressed content about housing bill B.",
                ],
                "notes": "Council passed a good cause eviction package on Nov 1.",
                "legislation_summary": sample_writer_output,
                "findings": ["https://toronto.ca/council/agenda/2024-11-01/"],
                "overview": "Housing policy update for Toronto.",
            }
        },
    }
