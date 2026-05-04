"""
Email template rendering.

Loads the branded HTML template from disk, converts markdown report bodies
to HTML, and fills the template placeholders (topic sections, TOC, social
share URLs, main content).
"""

import os
import logging
from datetime import datetime
from functools import lru_cache

import markdown

from utils.email.components import build_social_share_urls

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_template() -> str:
    """Load the email template from disk (cached after first load).

    Returns:
        HTML email template string

    Raises:
        FileNotFoundError: If template file not found
    """
    template_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "templates", "email_report.html"
    )

    try:
        with open(template_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Email template not found at {template_path}")
        raise


def convert_markdown_to_html(markdown_content: str) -> str:
    """Convert markdown content to HTML.

    Args:
        markdown_content: Markdown text to convert

    Returns:
        HTML representation of the markdown
    """
    return markdown.markdown(markdown_content)


def render_template(
    html_content: str,
    topic_sections_html: str | None = None,
    social_share_urls: dict[str, str] | None = None,
    table_of_contents_html: str | None = None,
    city: str = "",
    unsubscribe_url: str = "#",
) -> str:
    """Render the email template with HTML content and optional social share URLs.

    Args:
        html_content: HTML content to insert into template.
        topic_sections_html: Optional HTML for topic sections to replace {{TOPIC_SECTIONS}}.
        social_share_urls: Optional dict with 'twitter', 'facebook', 'linkedin' share URLs.
                           If None, default URLs (without referral code) are used.
        table_of_contents_html: Optional HTML for the table of contents to replace
                                {{TABLE_OF_CONTENTS}}. If None, the placeholder is removed.
        city: City name used to build the header title and date line.
        unsubscribe_url: Unsubscribe link inserted into the footer. Defaults to '#'.

    Returns:
        Complete HTML email body.
    """
    now = datetime.now()
    day = now.day
    date_str = now.strftime(f"%B {day}, %Y").upper()

    city_header = f"What's new in {city}?" if city else "What's new?"
    header_date = f"{date_str} | {city.upper()}" if city else date_str

    template = load_template()
    template = template.replace("{{CITY_HEADER}}", city_header)
    template = template.replace("{{HEADER_DATE}}", header_date)
    template = template.replace("{{TABLE_OF_CONTENTS}}", table_of_contents_html or "")
    template = template.replace("{{TOPIC_SECTIONS}}", topic_sections_html or "")
    rendered = template.replace("{{CONTENT}}", html_content)

    if social_share_urls is None:
        social_share_urls = build_social_share_urls()

    rendered = rendered.replace("{{TWITTER_SHARE_URL}}", social_share_urls["twitter"])
    rendered = rendered.replace("{{FACEBOOK_SHARE_URL}}", social_share_urls["facebook"])
    rendered = rendered.replace("{{LINKEDIN_SHARE_URL}}", social_share_urls["linkedin"])
    rendered = rendered.replace("{{UNSUBSCRIBE_URL}}", unsubscribe_url)

    return rendered
