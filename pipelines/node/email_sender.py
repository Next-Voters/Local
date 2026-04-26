"""
Email sender node for the NV Local pipeline chain.

This module is part of the pipeline chain and sends reports to all subscribers
(not city-specific). It has been refactored to use the shared SMTP connection
pool from utils.email.

Note: Email dispatch is now primarily handled by the batch dispatcher
(pipelines/node/email_dispatcher.py) which sends city-specific reports.
This node is maintained for backward compatibility.
"""

import logging
import queue
import time
from concurrent.futures import ThreadPoolExecutor

from langchain_core.runnables import RunnableLambda

from utils.email.smtp import SMTPConnectionPool, send_single_email, is_email_configured
from utils.email.templates import convert_markdown_to_html, render_template
from utils.schemas.state import ChainData

logger = logging.getLogger(__name__)


def get_subscribers() -> list[str]:
    """Query subscribers from Supabase.

    Returns:
        List of subscriber email addresses
    """
    try:
        from utils.supabase_client import get_subscribers_for_city

        # For backward compatibility with pipeline-based sending,
        # we could implement city-specific logic here if needed
        # For now, this is not called in the main pipeline
        return []
    except Exception as e:
        logger.error(f"Failed to get subscribers: {e}")
        return []


def send_batch(
    pool: SMTPConnectionPool,
    emails: list[str],
    subject: str,
    html_body: str,
    failures_queue: queue.Queue,
):
    """Send emails in a batch using thread pool.

    Args:
        pool: SMTP connection pool
        emails: List of recipient email addresses
        subject: Email subject line
        html_body: HTML email body
        failures_queue: Thread-safe queue for tracking failures
    """
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for email in emails:
            future = executor.submit(
                send_single_email,
                pool,
                email,
                subject,
                html_body,
                failures_queue,
            )
            futures.append(future)
        for future in futures:
            future.result()


def send_email_to_subscribers(inputs: ChainData) -> ChainData:
    """Send email to all subscribers (legacy pipeline node).

    This node sends reports to ALL subscribers regardless of city preference.
    For city-specific dispatching, use dispatch_emails_to_subscribers() instead.

    Args:
        inputs: Pipeline state containing markdown_report

    Returns:
        Unchanged inputs (side effect: emails sent)
    """
    if not is_email_configured():
        logger.info("Email not configured; skipping email send")
        return inputs

    markdown_report = inputs.get("markdown_report")

    if not markdown_report:
        logger.warning("No markdown report in pipeline state")
        return inputs

    emails = get_subscribers()

    if not emails:
        logger.info("No subscribers found for email send")
        return inputs

    logger.info(f"Sending report email to {len(emails)} subscriber(s)")

    html_content = convert_markdown_to_html(markdown_report)
    section = (
        '<tr><td style="padding-top: 16px; font-family: -apple-system, '
        "BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; "
        'font-size: 15px; color: #1A1A1A; line-height: 1.6;">'
        f"{html_content}</td></tr>"
    )
    html_body = render_template(section)

    try:
        pool = SMTPConnectionPool(pool_size=10)
    except RuntimeError as e:
        logger.error(f"Failed to initialize SMTP pool: {e}")
        return inputs

    failures_queue: queue.Queue = queue.Queue()

    with pool:
        waves = [emails[i : i + 100] for i in range(0, len(emails), 100)]

        for wave in waves:
            send_batch(
                pool, wave, "NV Local Report", html_body, failures_queue
            )
            time.sleep(1)

    # Log any failures
    failure_count = 0
    while not failures_queue.empty():
        try:
            failure = failures_queue.get_nowait()
            logger.warning(f"Email delivery failed for {failure['email']}: {failure['error']}")
            failure_count += 1
        except queue.Empty:
            break

    if failure_count > 0:
        logger.warning(f"{failure_count} email delivery failure(s) encountered")

    return inputs


email_sender_chain = RunnableLambda(send_email_to_subscribers)