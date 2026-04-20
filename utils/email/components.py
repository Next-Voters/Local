"""
HTML component builders for branded emails.

These functions assemble discrete pieces of email HTML — topic sections,
table of contents, per-topic share rows, and social share URLs — which the
top-level template renderer weaves into the final email body.
"""

from urllib.parse import quote


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
        sections.append(build_topic_section_html(name, content, topic_color=color))
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
