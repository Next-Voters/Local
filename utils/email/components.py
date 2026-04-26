"""
HTML component builders for minimal text-first emails.

These functions assemble the small set of HTML pieces the new template
expects: the intro greeting block and the topic sections. The previous
branded components (TOC, social share, accent borders) have been removed
to match the text-first design.
"""

from urllib.parse import quote


BASE_SHARE_URL = "https://nextvoters.com/request-region"
SHARE_TEXT = "Stay informed about your local politics with free weekly reports from Next Voters"

SANS_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
)


def build_social_share_urls(
    referral_code: str | None = None,
    city: str | None = None,
    topic: str | None = None,
) -> dict[str, str]:
    """Build social share URLs for Twitter/X, Facebook, and LinkedIn.

    Retained because callers still construct these for tracking, even though
    the minimal template no longer renders share buttons.
    """
    page_url = BASE_SHARE_URL
    if referral_code:
        page_url = f"{BASE_SHARE_URL}?ref={quote(referral_code, safe='')}"

    if city and topic:
        share_text = (
            f"Check out what's happening in {city} on {topic} — "
            f"stay informed with Next Voters"
        )
    else:
        share_text = SHARE_TEXT

    encoded_url = quote(page_url, safe="")
    encoded_text = quote(share_text, safe="")

    return {
        "twitter": f"https://twitter.com/intent/tweet?text={encoded_text}&url={encoded_url}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={encoded_url}",
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_url}",
    }


def build_intro_html(city: str | None = None) -> str:
    """Build the greeting + framing paragraph that opens the email.

    Matches the text-first style: a one-line greeting addressed to the city's
    residents, followed by a single framing sentence about what's in the brief.
    """
    city_label = (city or "").strip() or "your community"
    residents = f"{city_label} residents" if city_label != "your community" else city_label
    return (
        f'<p style="font-family: {SANS_STACK}; font-size: 15px; color: #1A1A1A; '
        f'line-height: 1.55; margin: 0 0 12px 0;">Good morning, {residents}.</p>'
        f'<p style="font-family: {SANS_STACK}; font-size: 15px; color: #1A1A1A; '
        f'line-height: 1.55; margin: 0 0 24px 0;">'
        f"Here's what {city_label} actually did this week — organized by topic, "
        f"every claim cited.</p>"
    )


def build_topic_section_html(topic_name: str, html_content: str) -> str:
    """Build a single topic section: small-caps label + content.

    The label is rendered in tracked-out uppercase with a thin gray rule above,
    matching the minimal newsletter style. The content (already HTML-converted
    markdown) sits underneath in plain prose.
    """
    return f"""
    <tr>
      <td style="padding-top: 24px;">
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
          <tr>
            <td style="border-top: 1px solid #D9D9D9; padding-top: 14px;">
              <span style="font-family: {SANS_STACK}; font-size: 12px; color: #555555; letter-spacing: 1.5px; text-transform: uppercase; font-weight: 700;">{topic_name.upper()}</span>
            </td>
          </tr>
          <tr>
            <td style="padding-top: 6px; font-family: {SANS_STACK}; font-size: 15px; color: #1A1A1A; line-height: 1.6;">
              {html_content}
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def build_all_topic_sections_html(
    topics: list[tuple[str, str]],
    referral_code: str | None = None,
    city: str | None = None,
) -> str:
    """Build combined HTML for all topic sections.

    Args:
        topics: List of (topic_name, html_content) tuples.
        referral_code: Unused; retained for API compatibility with callers.
        city: Unused; retained for API compatibility with callers.

    Returns:
        Combined HTML string for all topic sections.
    """
    if not topics:
        return ""
    return "\n".join(build_topic_section_html(name, content) for name, content in topics)
