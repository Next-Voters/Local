"""
Email utilities for SMTP operations.

This module provides a thread-safe SMTP connection pool and email helper
functions that are used by both the pipeline email sender and batch dispatcher.
"""

import os
import smtplib
import ssl
import queue
import logging
from datetime import datetime, timezone
from functools import lru_cache
from email.mime.text import MIMEText
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

import markdown

logger = logging.getLogger(__name__)

# SMTP Configuration - Read from environment or use defaults
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

EMAIL_REQUIRED_ENV = (
    "SMTP_EMAIL",
    "SMTP_APP_PASSWORD",
    "SUPABASE_URL",
    "SUPABASE_KEY",
)


def is_email_configured() -> bool:
    """Check if all required email environment variables are set."""
    return all(os.environ.get(env_var) for env_var in EMAIL_REQUIRED_ENV)


class SMTPConnectionPool:
    """Thread-safe connection pool for SMTP operations.

    Manages a pool of SMTP connections for concurrent email sending.
    Connections are initialized on pool creation and reused across
    concurrent operations. Supports context manager protocol for
    automatic cleanup.
    """

    def __init__(
        self,
        pool_size: int = 10,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
    ):
        """Initialize SMTP connection pool.

        Args:
            pool_size: Number of connections to maintain in the pool
            smtp_host: SMTP server hostname (defaults to environment or smtp.gmail.com)
            smtp_port: SMTP server port (defaults to environment or 587)
        """
        self.pool_size = pool_size
        self.smtp_host = smtp_host or SMTP_HOST
        self.smtp_port = smtp_port or SMTP_PORT
        self._pool: queue.Queue[smtplib.SMTP] = queue.Queue(maxsize=pool_size)
        self._created_connections = 0
        self._failed_connections = 0
        self._init_pool()

    def _create_connection(self) -> smtplib.SMTP:
        """Create a single SMTP connection.

        Returns:
            Initialized SMTP connection

        Raises:
            smtplib.SMTPException: If connection/authentication fails
        """
        try:
            context = ssl.create_default_context()
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(os.environ["SMTP_EMAIL"], os.environ["SMTP_APP_PASSWORD"])
            return server
        except Exception as e:
            self._failed_connections += 1
            logger.error(
                f"Failed to create SMTP connection ({self._failed_connections}/{self.pool_size}): {e}"
            )
            raise

    def _init_pool(self):
        """Initialize the connection pool with partial failure handling.

        Attempts to create all pool connections. If some fail, continues with
        fewer connections to degrade gracefully. Logs all failures for debugging.
        """
        logger.info(f"Initializing SMTP connection pool (size={self.pool_size})")

        for i in range(self.pool_size):
            try:
                conn = self._create_connection()
                self._pool.put_nowait(conn)
                self._created_connections += 1
            except Exception as e:
                logger.warning(
                    f"Connection {i + 1}/{self.pool_size} failed: {type(e).__name__}: {e}. "
                    f"Continuing with partial pool ({self._created_connections} connections available)"
                )
                # Continue with partial pool instead of crashing
                continue

        if self._created_connections == 0:
            logger.error(
                f"Failed to create any SMTP connections! Pool initialization failed completely."
            )
            raise RuntimeError(
                "SMTP connection pool initialization failed: could not create any connections"
            )

        if self._created_connections < self.pool_size:
            logger.warning(
                f"SMTP pool partially initialized: {self._created_connections}/{self.pool_size} connections"
            )

    def get_connection(self, timeout: int = 30) -> smtplib.SMTP:
        """Get a healthy connection from the pool, replacing stale ones.

        Validates the connection with an SMTP NOOP command after retrieval.
        If the connection has gone stale, it is discarded and a fresh one
        is created in its place.

        Args:
            timeout: Seconds to wait for a connection to become available

        Returns:
            Healthy SMTP connection

        Raises:
            queue.Empty: If timeout expires before connection available
            smtplib.SMTPException: If reconnection fails
        """
        conn = self._pool.get(timeout=timeout)
        try:
            conn.noop()
            return conn
        except (smtplib.SMTPException, OSError):
            try:
                conn.quit()
            except Exception:
                pass
            logger.debug("Replaced stale SMTP connection from pool")
            return self._create_connection()

    def return_connection(self, conn: smtplib.SMTP):
        """Return a connection to the pool if healthy, discard otherwise.

        Validates the connection with an SMTP NOOP before returning it.
        Dead connections are closed and discarded to prevent recycling
        broken connections back into the pool.

        Args:
            conn: SMTP connection to return
        """
        try:
            conn.noop()
            self._pool.put_nowait(conn)
        except (smtplib.SMTPException, OSError):
            try:
                conn.quit()
            except Exception:
                pass
            logger.debug("Discarded unhealthy SMTP connection")
        except queue.Full:
            try:
                conn.quit()
            except Exception:
                pass

    def close_all(self):
        """Close all connections in the pool."""
        closed = 0
        failed = 0

        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                break
            try:
                conn.quit()
                closed += 1
            except Exception:
                failed += 1

        if closed > 0 or failed > 0:
            logger.info(f"SMTP pool closed: {closed} connections closed, {failed} errors")

    def __enter__(self):
        """Support usage as a context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close all connections on context exit."""
        self.close_all()
        return False


@lru_cache(maxsize=1)
def load_template() -> str:
    """Load the email template from disk (cached after first load).

    Returns:
        HTML email template string

    Raises:
        FileNotFoundError: If template file not found
    """
    template_path = os.path.join(
        os.path.dirname(__file__), "..", "templates", "email_report.html"
    )

    try:
        with open(template_path, "r") as f:
            return f.read()
    except FileNotFoundError as e:
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


BASE_SHARE_URL = "https://nextvoters.com/request-region"
SHARE_TEXT = "Stay informed about your local politics with free weekly reports from Next Voters"


def build_social_share_urls(
    referral_code: str | None = None,
    city: str | None = None,
    topic: str | None = None,
) -> dict[str, str]:
    """Build social share URLs for Twitter/X, Facebook, and LinkedIn.

    Constructs platform-specific sharing URLs pointing to the Next Voters
    sign-up page. If a referral code is provided, it is appended as a
    query parameter. If city and topic are provided, contextual share text
    is used instead of the default.

    Args:
        referral_code: Optional referral code to append as ?ref=CODE
        city: Optional city name for contextual share text
        topic: Optional topic name for contextual share text

    Returns:
        Dictionary with keys 'twitter', 'facebook', 'linkedin' mapping to share URLs.
    """
    page_url = BASE_SHARE_URL
    if referral_code:
        page_url = f"{BASE_SHARE_URL}?ref={quote(referral_code, safe='')}"

    if city and topic:
        share_text = f"Check out what's happening in {city} on {topic} — stay informed with Next Voters"
    else:
        share_text = SHARE_TEXT

    encoded_url = quote(page_url, safe="")
    encoded_text = quote(share_text, safe="")

    return {
        "twitter": f"https://twitter.com/intent/tweet?text={encoded_text}&url={encoded_url}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={encoded_url}",
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}",
    }


TOPIC_COLOR_MAP: dict[str, str] = {
    "Immigration": "#2563EB",
    "Civil Rights": "#7C3AED",
    "Economy": "#059669",
}
DEFAULT_TOPIC_COLOR = "#E63946"


def get_topic_color(topic_name: str) -> str:
    """Look up the accent color for a topic, falling back to the default red.

    Args:
        topic_name: The topic name to look up (case-insensitive match).

    Returns:
        Hex color string for the topic.
    """
    for key, color in TOPIC_COLOR_MAP.items():
        if key.lower() == topic_name.lower():
            return color
    return DEFAULT_TOPIC_COLOR


def build_topic_share_row_html(twitter_url: str, facebook_url: str, linkedin_url: str) -> str:
    """Return a compact inline share row for use inside topic sections.

    Renders smaller 32x32 share buttons with a 'Share this topic' micro-label,
    suitable for embedding after each topic's content.

    Args:
        twitter_url: Twitter/X share URL
        facebook_url: Facebook share URL
        linkedin_url: LinkedIn share URL

    Returns:
        HTML string for the inline share row.
    """
    return f"""
      <tr>
        <td style="padding: 10px 0 5px 0;">
          <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
            <tr>
              <td align="center" style="padding-bottom: 6px;">
                <span style="font-family: 'DM Sans', Arial, sans-serif; font-size: 11px; color: #888888; text-transform: uppercase; letter-spacing: 1px;">Share this topic</span>
              </td>
            </tr>
            <tr>
              <td align="center">
                <table role="presentation" border="0" cellspacing="0" cellpadding="0">
                  <tr>
                    <td align="center" style="padding: 0 4px;">
                      <a href="{twitter_url}" target="_blank" style="display: inline-block; width: 32px; height: 32px; line-height: 32px; background-color: #1A1A1A; border-radius: 6px; text-align: center; text-decoration: none; font-family: 'DM Sans', Arial, sans-serif; font-size: 13px; font-weight: 700; color: #FFFFFF;">X</a>
                    </td>
                    <td align="center" style="padding: 0 4px;">
                      <a href="{facebook_url}" target="_blank" style="display: inline-block; width: 32px; height: 32px; line-height: 32px; background-color: #1877F2; border-radius: 6px; text-align: center; text-decoration: none; font-family: 'DM Sans', Arial, sans-serif; font-size: 13px; font-weight: 700; color: #FFFFFF;">f</a>
                    </td>
                    <td align="center" style="padding: 0 4px;">
                      <a href="{linkedin_url}" target="_blank" style="display: inline-block; width: 32px; height: 32px; line-height: 32px; background-color: #0A66C2; border-radius: 6px; text-align: center; text-decoration: none; font-family: 'DM Sans', Arial, sans-serif; font-size: 13px; font-weight: 700; color: #FFFFFF;">in</a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>"""


def build_topic_section_html(
    topic_name: str,
    html_content: str,
    topic_color: str = DEFAULT_TOPIC_COLOR,
    share_row_html: str = "",
) -> str:
    """Build HTML for a single topic section with header, content, and optional share row.

    Args:
        topic_name: Display name for the topic header.
        html_content: Rendered HTML body for the topic.
        topic_color: Hex color for the left accent border (default: #E63946).
        share_row_html: Optional inline share row HTML to append after content.

    Returns:
        HTML string for the complete topic section.
    """
    return f"""
    <tr>
      <td style="padding: 0 35px;">
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td style="padding-top: 25px; padding-bottom: 8px;">
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="background-color: #F8F8F5; border-left: 4px solid {topic_color}; padding: 12px 20px;">
                    <span style="font-family: 'Bebas Neue', Impact, sans-serif; font-size: 22px; color: #1A1A1A; letter-spacing: 2px; text-transform: uppercase;">{topic_name}</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding: 15px 0 25px 0; font-family: 'DM Sans', Arial, sans-serif; font-size: 14px; color: #333333; line-height: 1.7;">
              {html_content}
            </td>
          </tr>
          {share_row_html}
        </table>
      </td>
    </tr>"""

def build_topic_divider_html() -> str:
    """Build HTML divider between topic sections.

    Uses a 2px gradient-style divider for stronger visual separation.
    """
    return """
    <tr>
      <td style="padding: 0 35px;">
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td style="height: 2px; background: linear-gradient(to right, #E63946, #E8E8E4, #E63946);"></td>
          </tr>
        </table>
      </td>
    </tr>"""

def build_all_topic_sections_html(
    topics: list[tuple[str, str]],
    referral_code: str | None = None,
    city: str | None = None,
) -> str:
    """Build combined HTML for all topic sections with dividers between them.

    For each topic, looks up its accent color and generates per-topic share
    URLs (with optional referral code and city context). A compact share row
    is appended after each topic's content.

    Args:
        topics: List of (topic_name, html_content) tuples.
        referral_code: Optional referral code for share URLs.
        city: Optional city name for contextual share text.

    Returns:
        Combined HTML string for all topic sections.
    """
    if not topics:
        return ""
    sections = []
    for i, (name, content) in enumerate(topics):
        color = get_topic_color(name)
        topic_share_urls = build_social_share_urls(referral_code, city, name)
        share_row = build_topic_share_row_html(
            topic_share_urls["twitter"],
            topic_share_urls["facebook"],
            topic_share_urls["linkedin"],
        )
        sections.append(build_topic_section_html(name, content, topic_color=color, share_row_html=share_row))
        if i < len(topics) - 1:
            sections.append(build_topic_divider_html())
    return "\n".join(sections)


def build_table_of_contents_html(topic_names: list[str]) -> str:
    """Build an HTML table-of-contents section listing topic names.

    Each topic is rendered as a list item with a colored accent dot matching
    its topic color from TOPIC_COLOR_MAP.

    Args:
        topic_names: List of topic names to include in the TOC.

    Returns:
        HTML string for the TOC section, or empty string if no topics.
    """
    if not topic_names:
        return ""

    items = []
    for name in topic_names:
        color = get_topic_color(name)
        items.append(
            f'<li style="font-family: \'DM Sans\', Arial, sans-serif; font-size: 14px; '
            f'color: #333333; padding: 4px 0; list-style: none;">'
            f'<span style="display: inline-block; width: 8px; height: 8px; '
            f'border-radius: 50%; background-color: {color}; margin-right: 10px; '
            f'vertical-align: middle;"></span>{name}</li>'
        )

    items_html = "\n".join(items)
    return f"""
    <tr>
      <td style="padding: 20px 35px 0 35px;">
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td style="background-color: #F5F5F0; border-radius: 8px; padding: 18px 24px;">
              <span style="font-family: 'Bebas Neue', Impact, sans-serif; font-size: 16px; color: #1A1A1A; letter-spacing: 2px; text-transform: uppercase; display: block; padding-bottom: 8px;">In This Report</span>
              <ul style="margin: 0; padding: 0;">
                {items_html}
              </ul>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def render_template(
    html_content: str,
    topic_sections_html: str | None = None,
    social_share_urls: dict[str, str] | None = None,
    table_of_contents_html: str | None = None,
) -> str:
    """Render the email template with HTML content and optional social share URLs.

    Args:
        html_content: HTML content to insert into template
        topic_sections_html: Optional HTML for topic sections to replace {{TOPIC_SECTIONS}}.
        social_share_urls: Optional dict with 'twitter', 'facebook', 'linkedin' share URLs.
                           If None, default URLs (without referral code) are used.
        table_of_contents_html: Optional HTML for the table of contents to replace
                                {{TABLE_OF_CONTENTS}}. If None, the placeholder is removed.

    Returns:
        Complete HTML email body.
    """
    template = load_template()
    template = template.replace("{{TABLE_OF_CONTENTS}}", table_of_contents_html or "")
    if topic_sections_html is not None:
        template = template.replace("{{TOPIC_SECTIONS}}", topic_sections_html)
    rendered = template.replace("{{CONTENT}}", html_content)

    if social_share_urls is None:
        social_share_urls = build_social_share_urls()

    rendered = rendered.replace("{{TWITTER_SHARE_URL}}", social_share_urls["twitter"])
    rendered = rendered.replace("{{FACEBOOK_SHARE_URL}}", social_share_urls["facebook"])
    rendered = rendered.replace("{{LINKEDIN_SHARE_URL}}", social_share_urls["linkedin"])

    return rendered


def create_mime_message(
    from_email: str,
    to_email: str,
    subject: str,
    html_body: str,
) -> MIMEText:
    """Create a MIME email message.

    Args:
        from_email: Sender email address
        to_email: Recipient email address
        subject: Email subject line
        html_body: HTML email body

    Returns:
        MIMEText message object ready to send
    """
    msg = MIMEText(html_body, "html", "utf-8")
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    return msg


def send_single_email(
    pool: SMTPConnectionPool,
    email: str,
    subject: str,
    html_body: str,
    failures: queue.Queue,
) -> bool:
    """Send a single email using a pooled connection and track failures.

    Retrieves a connection from the pool, sends the email, and returns
    the connection. On failure, the error is recorded to the thread-safe
    failures queue and the connection is returned (the pool's health check
    will discard it if it is no longer usable).

    Args:
        pool: SMTP connection pool
        email: Recipient email address
        subject: Email subject line
        html_body: HTML email body
        failures: Thread-safe queue for tracking delivery failures

    Returns:
        True if email sent successfully, False otherwise
    """
    conn = None
    try:
        conn = pool.get_connection(timeout=30)

        msg = create_mime_message(
            os.environ["SMTP_EMAIL"],
            email,
            subject,
            html_body,
        )

        conn.sendmail(os.environ["SMTP_EMAIL"], email, msg.as_string())

        return True
    except Exception as e:
        failures.put(
            {
                "email": email,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return False
    finally:
        if conn:
            pool.return_connection(conn)