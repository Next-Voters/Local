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
from functools import lru_cache
from email.mime.text import MIMEText

import markdown

logger = logging.getLogger(__name__)

# SMTP Configuration - Read from environment or use defaults
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


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
        """Get a connection from the pool.
        
        Args:
            timeout: Seconds to wait for a connection to become available
            
        Returns:
            SMTP connection
            
        Raises:
            queue.Empty: If timeout expires before connection available
        """
        return self._pool.get(timeout=timeout)

    def return_connection(self, conn: smtplib.SMTP):
        """Return a connection to the pool for reuse.
        
        Args:
            conn: SMTP connection to return
        """
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            # Pool is full, close this connection
            try:
                conn.quit()
            except Exception as e:
                logger.debug(f"Error closing excess connection: {e}")

    def close_all(self):
        """Close all connections in the pool."""
        closed = 0
        failed = 0
        
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.quit()
                closed += 1
            except Exception as e:
                failed += 1
                logger.debug(f"Error closing connection during cleanup: {e}")
        
        if closed > 0 or failed > 0:
            logger.info(f"SMTP pool closed: {closed} connections closed, {failed} errors")


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


def render_template(html_content: str) -> str:
    """Render the email template with HTML content.
    
    Args:
        html_content: HTML content to insert into template
        
    Returns:
        Complete HTML email body
    """
    template = load_template()
    return template.replace("{{CONTENT}}", html_content)


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
