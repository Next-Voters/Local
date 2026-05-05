"""Upload HTML reports to Supabase Storage."""

import re
import logging
from datetime import date

from utils.supabase_client import get_supabase_client
from utils.email.templates import convert_markdown_to_html, render_template

logger = logging.getLogger(__name__)

BUCKET = "reports"


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug for storage paths."""
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


def _render(md: str, city: str = "") -> str:
    """Convert markdown to full branded HTML."""
    return render_template(convert_markdown_to_html(md), city=city)


def upload_report(city: str, topic: str, html: str) -> str | None:
    """Upload a single HTML report. Returns the storage path or None on failure."""
    path = f"{_slugify(city)}/{_slugify(topic)}/en/{date.today().isoformat()}.html"
    try:
        client = get_supabase_client()
        client.storage.from_(BUCKET).upload(
            path=path,
            file=html.encode("utf-8"),
            file_options={"content-type": "text/html", "upsert": "true"},
        )
        logger.info(f"Uploaded {BUCKET}/{path}")
        return path
    except Exception as e:
        logger.error(f"Failed to upload {path}: {e}")
        return None


def upload_all(reports: dict[str, dict[str, str]]) -> int:
    """Upload all reports as HTML to Supabase Storage.

    Args:
        reports: {city: {topic: markdown}}.

    Returns:
        Number of successfully uploaded files.
    """
    uploaded = 0

    for city, topics in reports.items():
        for topic, md in topics.items():
            if md and upload_report(city, topic, _render(md, city)):
                uploaded += 1

    logger.info(f"Storage upload complete: {uploaded} files uploaded")
    return uploaded
