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
    concurrent operations.
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


def build_translation_html(translations_html: dict[str, str]) -> str:
    """Build styled HTML blocks for translated report sections.

    Args:
        translations_html: Dict mapping language code to translated HTML content.
                           Expected keys: "ES" (Spanish), "FR" (French).

    Returns:
        Combined HTML string with language-headed sections, or empty string.
    """
    lang_labels = {
        "ES": "Informe en Espa\u00f1ol",
        "FR": "Rapport en Fran\u00e7ais",
    }

    sections = []
    for lang_code in ("ES", "FR"):
        content = translations_html.get(lang_code, "")
        if not content:
            continue
        label = lang_labels.get(lang_code, lang_code)
        sections.append(
            f'<!-- TRANSLATION: {lang_code} -->\n'
            f'<tr>\n'
            f'    <td style="padding: 0 35px;">\n'
            f'        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">\n'
            f'            <tr><td style="height: 1px; background-color: #E63946;"></td></tr>\n'
            f'        </table>\n'
            f'    </td>\n'
            f'</tr>\n'
            f'<tr>\n'
            f'    <td style="background-color: #1A1A1A; padding: 10px 35px;">\n'
            f'        <p style="font-family: \'DM Sans\', Arial, sans-serif; font-size: 13px; color: #FFFFFF; margin: 0; letter-spacing: 1px; font-weight: 500;">{label}</p>\n'
            f'    </td>\n'
            f'</tr>\n'
            f'<tr>\n'
            f'    <td style="padding: 30px 35px;">\n'
            f'        {content}\n'
            f'    </td>\n'
            f'</tr>'
        )

    return "\n".join(sections)


def render_template(html_content: str, translations_html: dict[str, str] | None = None) -> str:
    """Render the email template with HTML content and optional translations.

    Args:
        html_content: HTML content to insert into the main content area.
        translations_html: Optional dict mapping language code ("ES", "FR")
                           to translated HTML content.

    Returns:
        Complete HTML email body.
    """
    template = load_template()
    result = template.replace("{{CONTENT}}", html_content)

    translation_block = build_translation_html(translations_html or {})
    result = result.replace("{{TRANSLATIONS}}", translation_block)

    return result


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
