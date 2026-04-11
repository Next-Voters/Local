"""Domain-level source reliability scoring for legislation research.

Zero-dependency module that evaluates URLs based on domain patterns,
TLD classification, and URL path signals. No API keys required.

Tiers:
    1 (government)   — Official government domains (.gov, city portals)
    2 (legislative)   — Known legislative platforms (Legistar, Municode, etc.)
    3 (news)          — Established news outlets and wire services
    4 (other)         — Everything else that isn't explicitly blocked
    0 (blocked)       — Known low-quality domains (blogs, social media, petitions)
"""

import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier 1 — Government domain patterns
# ---------------------------------------------------------------------------

# TLDs that are exclusively government-controlled
_GOV_TLDS = {".gov", ".gov.uk", ".gc.ca", ".gov.au", ".govt.nz"}

# Patterns in the domain that indicate a government site (city/municipal portals).
# These match domains like toronto.ca, nyc.gov, sandiego.gov, etc.
_GOV_DOMAIN_PATTERNS = re.compile(
    r"""
    \.gov(\.[a-z]{2})?$          |  # any .gov or .gov.xx TLD
    \.gc\.ca$                    |  # Government of Canada
    \.parliament\.(uk|ca)$       |  # Parliaments
    \.legislature\.               |  # State/provincial legislatures
    \.assembly\.                  |  # Legislative assemblies
    ^(www\.)?toronto\.ca$        |  # Toronto
    ^secure\.toronto\.ca$        |  # Toronto council portal
    ^app\.toronto\.ca$           |  # Toronto TMMIS
    ^(www\.)?nyc\.gov$           |  # New York City
    ^(www\.)?sandiego\.gov$      |  # San Diego
    ^(www\.)?chicago\.gov$       |  # Chicago
    ^(www\.)?lacity\.gov$        |  # Los Angeles
    ^(www\.)?boston\.gov$         |  # Boston
    ^(www\.)?seattle\.gov$       |  # Seattle
    ^(www\.)?sf\.gov$            |  # San Francisco
    ^(www\.)?phila\.gov$         |  # Philadelphia
    ^(www\.)?houston\.gov$       |  # Houston
    ^(www\.)?dallascityhall\.com$|  # Dallas
    ^(www\.)?ottawa\.ca$         |  # Ottawa
    ^(www\.)?vancouver\.ca$      |  # Vancouver
    ^(www\.)?montreal\.ca$       |  # Montreal
    ^(www\.)?calgary\.ca$        |  # Calgary
    ^(www\.)?edmonton\.ca$       |  # Edmonton
    ^(www\.)?winnipeg\.ca$          # Winnipeg
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tier 2 — Legislative platform domains
# ---------------------------------------------------------------------------

_LEGISLATIVE_DOMAINS = {
    "legistar.com",
    "municode.com",
    "granicus.com",
    "escribe.com",
    "civicclerk.com",
    "boarddocs.com",
    "govtrack.us",
    "ballotpedia.org",
    "congress.gov",
    "legis.state",
    "capitol.texas.gov",
    "leginfo.legislature.ca.gov",
    "parl.ca",
    "ola.org",
}

# ---------------------------------------------------------------------------
# Tier 3 — Established news outlets and wire services
# ---------------------------------------------------------------------------

_NEWS_DOMAINS = {
    # Wire services
    "apnews.com",
    "reuters.com",
    "upi.com",
    "afp.com",
    # US national
    "nytimes.com",
    "washingtonpost.com",
    "usatoday.com",
    "latimes.com",
    "chicagotribune.com",
    "sfchronicle.com",
    "bostonglobe.com",
    "dallasnews.com",
    "seattletimes.com",
    "sandiegouniontribune.com",
    "houstonchronicle.com",
    "miamiherald.com",
    "denverpost.com",
    "startribune.com",
    "phillymag.com",
    "inquirer.com",
    "politico.com",
    "thehill.com",
    "axios.com",
    "nbcnews.com",
    "cbsnews.com",
    "abcnews.go.com",
    "foxnews.com",
    "cnn.com",
    "npr.org",
    "pbs.org",
    # Canadian
    "cbc.ca",
    "globalnews.ca",
    "thestar.com",
    "theglobeandmail.com",
    "nationalpost.com",
    "ctvnews.ca",
    "cp24.com",
    "vancouversun.com",
    "montrealgazette.com",
    "ottawacitizen.com",
    "calgaryherald.com",
    "edmontonjournal.com",
    # UK / International
    "bbc.com",
    "bbc.co.uk",
    "theguardian.com",
    "independent.co.uk",
    "economist.com",
    "ft.com",
    "aljazeera.com",
    # Public broadcasting / non-profit
    "propublica.org",
    "theconversation.com",
    "thetyee.ca",
}

# ---------------------------------------------------------------------------
# Tier 0 — Blocked domains (social media, blogs, petitions, UGC)
# ---------------------------------------------------------------------------

_BLOCKED_DOMAINS = {
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "quora.com",
    "youtube.com",
    "medium.com",
    "substack.com",
    "blogspot.com",
    "wordpress.com",
    "tumblr.com",
    "change.org",
    "yelp.com",
    "nextdoor.com",
    "pinterest.com",
    "linkedin.com",
    "4chan.org",
}

# URL path segments that signal opinion/editorial content
_OPINION_PATH_PATTERNS = re.compile(
    r"/opinion/|/editorial/|/op-ed/|/blog/|/column/|/letters/",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_url(url: str) -> dict:
    """Score a single URL for source reliability.

    Returns:
        dict with keys: url, domain, tier (0-4), tier_name, reason
    """
    try:
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower().lstrip("www.")
        full_domain = (parsed.hostname or "").lower()
        path = parsed.path or ""
    except Exception:
        return {"url": url, "domain": "", "tier": 0, "tier_name": "blocked", "reason": "Unparseable URL"}

    # Check blocked domains first
    if domain in _BLOCKED_DOMAINS or any(domain.endswith(f".{d}") for d in _BLOCKED_DOMAINS):
        return {"url": url, "domain": domain, "tier": 0, "tier_name": "blocked", "reason": "Known low-quality domain"}

    # Check opinion/editorial path patterns (demote to tier 4 regardless of domain)
    if _OPINION_PATH_PATTERNS.search(path):
        return {"url": url, "domain": domain, "tier": 4, "tier_name": "other", "reason": "Opinion/editorial URL path"}

    # Tier 1: Government
    if _GOV_DOMAIN_PATTERNS.search(full_domain):
        return {"url": url, "domain": domain, "tier": 1, "tier_name": "government", "reason": "Government domain"}

    # Also check TLD-based government detection for domains not in the pattern list
    for gov_tld in _GOV_TLDS:
        if full_domain.endswith(gov_tld):
            return {"url": url, "domain": domain, "tier": 1, "tier_name": "government", "reason": f"Government TLD ({gov_tld})"}

    # Tier 2: Legislative platforms
    if domain in _LEGISLATIVE_DOMAINS or any(domain.endswith(f".{d}") for d in _LEGISLATIVE_DOMAINS):
        return {"url": url, "domain": domain, "tier": 2, "tier_name": "legislative", "reason": "Legislative platform"}

    # Tier 3: News outlets
    if domain in _NEWS_DOMAINS or any(domain.endswith(f".{d}") for d in _NEWS_DOMAINS):
        return {"url": url, "domain": domain, "tier": 3, "tier_name": "news", "reason": "Established news outlet"}

    # Tier 4: Everything else
    return {"url": url, "domain": domain, "tier": 4, "tier_name": "other", "reason": "Unrecognized domain"}


def filter_sources(urls: list[str], min_tier: int = 4) -> list[dict]:
    """Score and filter a list of URLs.

    Args:
        urls: List of URLs to evaluate.
        min_tier: Maximum tier number to accept (1=gov only, 2=+legislative,
                  3=+news, 4=+other, 0 is always blocked). Default 4 accepts all
                  non-blocked URLs.

    Returns:
        List of score dicts for accepted URLs, sorted by tier (best first).
    """
    scored = [score_url(url) for url in urls]

    accepted = [s for s in scored if 1 <= s["tier"] <= min_tier]
    blocked = [s for s in scored if s["tier"] == 0]
    demoted = [s for s in scored if s["tier"] > min_tier]

    for s in accepted:
        logger.info("  ACCEPT [tier %d/%s] %s — %s", s["tier"], s["tier_name"], s["url"], s["reason"])
    for s in blocked:
        logger.info("  BLOCK  %s — %s", s["url"], s["reason"])
    for s in demoted:
        logger.info("  DEMOTE [tier %d/%s] %s — %s", s["tier"], s["tier_name"], s["url"], s["reason"])

    # Sort by tier (government first, then legislative, then news, then other)
    accepted.sort(key=lambda s: s["tier"])
    return accepted
