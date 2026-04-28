"""
Email template rendering.

Loads the minimal HTML template from disk, converts markdown report bodies
to HTML, and fills the template placeholders (intro, topic sections).
"""

import os
import logging
from functools import lru_cache

import markdown

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
    """Convert markdown content to HTML."""
    return markdown.markdown(markdown_content)


def render_template(
    topic_sections_html: str,
    intro_html: str = "",
    unsubscribe_url: str = "#",
) -> str:
    """Render the minimal email template.

    Args:
        topic_sections_html: HTML for the topic sections, replaces {{TOPIC_SECTIONS}}.
        intro_html: HTML for the greeting + framing paragraphs at the top.
        unsubscribe_url: URL for the footer unsubscribe link.

    Returns:
        Complete HTML email body.
    """
    template = load_template()
    template = template.replace("{{INTRO_HTML}}", intro_html)
    template = template.replace("{{TOPIC_SECTIONS}}", topic_sections_html)
    template = template.replace("{{UNSUBSCRIBE_URL}}", unsubscribe_url)
    return template
