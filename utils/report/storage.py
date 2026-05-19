"""Save pipeline reports to the Supabase reports and report_headers tables."""

from datetime import date
from typing import Any

from utils.logger import get_logger
from utils.supabase_client import get_supabase_client

logger = get_logger(__name__)

# Module-level cache: topic_name -> topic_id
_topic_ids: dict[str, int] = {}


def _get_topic_id(topic_name: str) -> int | None:
    """Resolve a topic name to its integer ID, caching the result."""
    if topic_name in _topic_ids:
        return _topic_ids[topic_name]

    try:
        client = get_supabase_client()
        response = (
            client.table("supported_topics")
            .select("topic_id")
            .eq("topic_name", topic_name)
            .limit(1)
            .execute()
        )
        if response.data:
            tid = response.data[0]["topic_id"]
            _topic_ids[topic_name] = tid
            return tid
        logger.warning(f"No topic_id found for topic: {topic_name}")
        return None
    except Exception as e:
        logger.error(f"Failed to resolve topic_id for {topic_name}: {e}")
        return None


def save_report(region: str, topic_name: str, result: dict[str, Any]) -> int | None:
    """Save a pipeline result to the reports and report_headers tables.

    Upserts a parent report row for (region, today), then upserts one
    report_headers row per legislation item with the topic and bullets.

    Args:
        region: Region name (FK to regions).
        topic_name: Topic name string (resolved to topic_id).
        result: Pipeline result dict containing 'legislation_summary' (WriterOutput).

    Returns:
        The report ID (bigint PK) on success, or None on failure.
    """
    summary = result.get("legislation_summary")
    if summary is None:
        return None

    if not summary.items:
        logger.warning(f"No items to save for {region}/{topic_name}, skipping upsert")
        return None

    topic_id = _get_topic_id(topic_name)
    if topic_id is None:
        return None

    try:
        client = get_supabase_client()

        # Upsert parent report row: one per region per day
        report_response = client.table("reports").upsert(
            {
                "region": region,
                "report_date": date.today().isoformat(),
            },
            on_conflict="region,report_date",
        ).execute()

        report_id = report_response.data[0]["id"]

        # Delete stale headers for this (report_id, topic_id) before inserting
        client.table("report_headers").delete().eq(
            "report_id", report_id
        ).eq("topic_id", topic_id).execute()

        # Insert one report_headers row per legislation item
        headers = [
            {
                "report_id": report_id,
                "topic_id": topic_id,
                "header": item.header,
                "bullets": item.bullets,
            }
            for item in summary.items
        ]

        client.table("report_headers").insert(headers).execute()

        logger.info(
            f"Saved report: {region}/{topic_name} "
            f"(report_id={report_id}, headers={len(headers)})"
        )
        return report_id

    except Exception as e:
        logger.error(f"Failed to save report {region}/{topic_name}: {e}")
        return None
