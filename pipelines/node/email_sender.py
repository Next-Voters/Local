import json
import os
import smtplib
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Lock

import markdown
from supabase import create_client, Client

from utils.schemas.state import ChainData


class SMTPConnectionPool:
    def __init__(self, pool_size=10, smtp_host="smtp.gmail.com", smtp_port=587):
        self.pool_size = pool_size
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.connections: list[smtplib.SMTP] = []
        self.lock = Lock()
        self._init_pool()

    def _create_connection(self) -> smtplib.SMTP:
        context = ssl.create_default_context()
        server = smtplib.SMTP(self.smtp_host, self.smtp_port)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(os.environ["SMTP_EMAIL"], os.environ["SMTP_APP_PASSWORD"])
        return server

    def _init_pool(self):
        for _ in range(self.pool_size):
            self.connections.append(self._create_connection())

    def get_connection(self) -> smtplib.SMTP:
        with self.lock:
            return self.connections.pop()

    def return_connection(self, conn: smtplib.SMTP):
        with self.lock:
            self.connections.append(conn)

    def close_all(self):
        with self.lock:
            for conn in self.connections:
                try:
                    conn.quit()
                except:
                    pass


def load_template() -> str:
    template_path = os.path.join(
        os.path.dirname(__file__), "..", "templates", "email_report.html"
    )
    with open(template_path, "r") as f:
        return f.read()


def convert_markdown_to_html(markdown_content: str) -> str:
    return markdown.markdown(markdown_content)


def render_template(html_content: str) -> str:
    template = load_template()
    return template.replace("{{CONTENT}}", html_content)


def get_subscribers() -> list[str]:
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_KEY"]
    client: Client = create_client(supabase_url, supabase_key)

    response = client.table("subscriptions").select("contact").execute()

    emails = []
    for item in response.data:
        contact = item.get("contact")
        if contact:
            emails.append(contact)

    return emails


def send_single_email(
    pool: SMTPConnectionPool,
    email: str,
    subject: str,
    html_body: str,
    failures: list[dict],
    failures_lock: Lock,
) -> bool:
    conn = None
    try:
        conn = pool.get_connection()

        msg = f"""From: {os.environ["SMTP_EMAIL"]}
To: {email}
Subject: {subject}
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

{html_body}
"""

        conn.sendmail(os.environ["SMTP_EMAIL"], email, msg)

        time.sleep(0.5)

        return True
    except Exception as e:
        with failures_lock:
            failures.append(
                {
                    "email": email,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        return False
    finally:
        if conn:
            pool.return_connection(conn)


def send_batch(
    pool: SMTPConnectionPool,
    emails: list[str],
    subject: str,
    html_body: str,
    failures: list[dict],
    failures_lock: Lock,
):
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for email in emails:
            future = executor.submit(
                send_single_email,
                pool,
                email,
                subject,
                html_body,
                failures,
                failures_lock,
            )
            futures.append(future)
        for future in futures:
            future.result()


def save_failures(failures: list[dict]):
    if not failures:
        return
    failures_path = os.path.join(os.path.dirname(__file__), "..", "email_failures.json")
    with open(failures_path, "w") as f:
        json.dump(failures, f, indent=2)


def send_email_to_subscribers(inputs: ChainData) -> ChainData:
    markdown_report = inputs.get("markdown_report")

    if not markdown_report:
        return inputs

    emails = get_subscribers()

    if not emails:
        return inputs

    html_content = convert_markdown_to_html(markdown_report)
    html_body = render_template(html_content)

    pool = SMTPConnectionPool(pool_size=10)
    failures: list[dict] = []
    failures_lock = Lock()

    try:
        waves = [emails[i : i + 100] for i in range(0, len(emails), 100)]

        for wave in waves:
            send_batch(
                pool, wave, "NV Local Report", html_body, failures, failures_lock
            )
            time.sleep(1)
    finally:
        pool.close_all()

    save_failures(failures)

    return inputs
