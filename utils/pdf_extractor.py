"""PDF detection and extraction utilities.

Provides deterministic PDF detection (HEAD request + suffix check) and
high-fidelity PDF-to-Markdown conversion via pymupdf4llm. Used by the
web_search tool to inline PDF content before it reaches content_retrieval.
"""

import logging

import httpx

from config.constants import MAX_PDF_SIZE_BYTES

logger = logging.getLogger(__name__)

# Timeout for the lightweight HEAD check (seconds).
_HEAD_TIMEOUT = 10.0

# Timeout for the full PDF download (seconds).
_DOWNLOAD_TIMEOUT = 30.0


def is_pdf_url(url: str) -> bool:
    """Determine whether *url* points to a PDF document.

    Checks the URL suffix first (cheap), then falls back to an HTTP HEAD
    request to inspect the Content-Type header. Returns ``False`` on any
    network error so the URL can still be handled by the normal HTML path.
    """
    if url.lower().rstrip("/").endswith(".pdf"):
        return True

    try:
        response = httpx.head(url, timeout=_HEAD_TIMEOUT, follow_redirects=True)
        content_type = response.headers.get("content-type", "").lower()
        return "application/pdf" in content_type
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return False


def download_and_parse_pdf(url: str) -> str:
    """Download a PDF from *url* and convert it to Markdown.

    Uses ``pymupdf4llm`` for layout-aware conversion that preserves tables,
    headings, and reading order — critical for legislative documents.

    Returns an empty string on any failure so the caller can fall back to
    the standard HTML extraction path.
    """
    try:
        import pymupdf4llm  # noqa: E402 — lazy import, heavy C extension
    except ImportError:
        logger.warning("pymupdf4llm is not installed — skipping PDF extraction.")
        return ""

    try:
        # Check Content-Length before downloading the full body.
        head = httpx.head(url, timeout=_HEAD_TIMEOUT, follow_redirects=True)
        content_length = int(head.headers.get("content-length", 0))
        if content_length > MAX_PDF_SIZE_BYTES:
            logger.info(
                "Skipping PDF (%.1f MB > %.1f MB limit): %s",
                content_length / (1024 * 1024),
                MAX_PDF_SIZE_BYTES / (1024 * 1024),
                url,
            )
            return ""

        response = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True)
        response.raise_for_status()

        # Double-check actual body size (Content-Length can be missing/wrong).
        if len(response.content) > MAX_PDF_SIZE_BYTES:
            logger.info("PDF body exceeds size limit after download: %s", url)
            return ""

        # pymupdf4llm can read from raw bytes via a pymupdf.Document stream.
        import pymupdf  # shipped with pymupdf4llm

        doc = pymupdf.Document(stream=response.content, filetype="pdf")
        markdown_text: str = pymupdf4llm.to_markdown(doc)
        doc.close()

        logger.info(
            "PDF extracted: %s → %d chars of Markdown", url, len(markdown_text)
        )
        return markdown_text.strip()

    except Exception as e:
        logger.warning("PDF extraction failed for %s: %s", url, e)
        return ""
