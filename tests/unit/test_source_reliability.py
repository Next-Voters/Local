"""Unit tests for utils/content/source_reliability.py.

Pure function tests — no mocking required.
"""


from utils.content.source_reliability import filter_sources, score_url


class TestScoreUrlTier1Government:
    def test_dot_gov_tld(self):
        result = score_url("https://nyc.gov/housing/plan")
        assert result["tier"] == 1
        assert result["tier_name"] == "government"

    def test_gc_ca_tld(self):
        result = score_url("https://canada.gc.ca/en/services")
        assert result["tier"] == 1
        assert result["tier_name"] == "government"

    def test_toronto_ca(self):
        result = score_url("https://toronto.ca/council/agenda/2024-11-01/")
        assert result["tier"] == 1
        assert result["tier_name"] == "government"

    def test_secure_toronto_ca(self):
        result = score_url("https://secure.toronto.ca/council/agendaItem.do?item=2024.EX20.1")
        assert result["tier"] == 1

    def test_vancouver_ca(self):
        result = score_url("https://vancouver.ca/your-government/city-council.aspx")
        assert result["tier"] == 1

    def test_sandiego_gov(self):
        result = score_url("https://www.sandiego.gov/planning")
        assert result["tier"] == 1

    def test_result_contains_url_and_domain(self):
        url = "https://boston.gov/news"
        result = score_url(url)
        assert result["url"] == url
        assert result["domain"] == "boston.gov"


class TestScoreUrlTier2Legislative:
    def test_legistar(self):
        result = score_url("https://toronto.legistar.com/LegislationDetail.aspx?ID=1234")
        assert result["tier"] == 2
        assert result["tier_name"] == "legislative"

    def test_municode(self):
        result = score_url("https://library.municode.com/ca/san_francisco/codes/code_of_ordinances")
        assert result["tier"] == 2

    def test_granicus(self):
        result = score_url("https://toronto.granicus.com/MediaPlayer.php?clip_id=1234")
        assert result["tier"] == 2

    def test_ballotpedia(self):
        result = score_url("https://ballotpedia.org/Toronto_City_Council")
        assert result["tier"] == 2


class TestScoreUrlTier3News:
    def test_nytimes(self):
        result = score_url("https://www.nytimes.com/2024/01/01/us/housing-bill.html")
        assert result["tier"] == 3
        assert result["tier_name"] == "news"

    def test_cbc_ca(self):
        result = score_url("https://www.cbc.ca/news/canada/toronto/housing-crisis")
        assert result["tier"] == 3

    def test_thestar(self):
        result = score_url("https://www.thestar.com/politics/2024-01-01-housing.html")
        assert result["tier"] == 3

    def test_reuters(self):
        result = score_url("https://www.reuters.com/world/us/housing-bill-2024")
        assert result["tier"] == 3


class TestScoreUrlTier0Blocked:
    def test_twitter(self):
        result = score_url("https://twitter.com/mayoroffice/status/123456")
        assert result["tier"] == 0
        assert result["tier_name"] == "blocked"

    def test_x_com(self):
        result = score_url("https://x.com/citycouncil/status/789")
        assert result["tier"] == 0

    def test_reddit(self):
        result = score_url("https://reddit.com/r/toronto/comments/abc/housing_discussion")
        assert result["tier"] == 0

    def test_medium(self):
        result = score_url("https://medium.com/@author/city-housing-analysis")
        assert result["tier"] == 0

    def test_facebook(self):
        result = score_url("https://facebook.com/mayorpage/posts/123")
        assert result["tier"] == 0


class TestScoreUrlOpinionDemotion:
    """Opinion/editorial paths demote even high-quality domains to tier 4."""

    def test_news_domain_opinion_path_demoted_to_tier4(self):
        result = score_url("https://www.nytimes.com/opinion/2024/01/housing-crisis.html")
        assert result["tier"] == 4
        assert result["tier_name"] == "other"
        assert "Opinion" in result["reason"] or "opinion" in result["reason"].lower()

    def test_blog_path_demoted(self):
        result = score_url("https://www.thestar.com/blog/2024/housing-policy")
        assert result["tier"] == 4

    def test_editorial_path_demoted(self):
        result = score_url("https://www.reuters.com/editorial/2024/analysis")
        assert result["tier"] == 4


class TestScoreUrlTier4Other:
    def test_unknown_domain(self):
        result = score_url("https://www.citycouncilwatch.net/toronto/2024")
        assert result["tier"] == 4
        assert result["tier_name"] == "other"

    def test_result_keys_present(self):
        result = score_url("https://example.com/page")
        assert {"url", "domain", "tier", "tier_name", "reason"} == set(result.keys())


class TestScoreUrlEdgeCases:
    def test_malformed_url_no_domain_is_tier4(self):
        # urlparse is lenient and never raises on malformed strings; a URL with
        # no recognisable domain simply falls through to tier 4 (other).
        result = score_url("not a url at all ://???")
        assert result["tier"] == 4
        assert result["tier_name"] == "other"

    def test_empty_string_is_tier4(self):
        # Empty string parses cleanly (domain=""); no patterns match → tier 4.
        result = score_url("")
        assert result["tier"] == 4
        assert result["tier_name"] == "other"


class TestFilterSources:
    def test_returns_only_non_blocked(self):
        urls = [
            "https://toronto.ca/council",
            "https://twitter.com/mayor",
            "https://legistar.com/toronto",
        ]
        result = filter_sources(urls)
        returned_urls = [r["url"] for r in result]
        assert "https://twitter.com/mayor" not in returned_urls
        assert "https://toronto.ca/council" in returned_urls
        assert "https://legistar.com/toronto" in returned_urls

    def test_sorted_by_tier_ascending(self):
        urls = [
            "https://www.nytimes.com/news",      # tier 3
            "https://toronto.ca/council",         # tier 1
            "https://legistar.com/toronto",       # tier 2
        ]
        result = filter_sources(urls)
        tiers = [r["tier"] for r in result]
        assert tiers == sorted(tiers)

    def test_min_tier_filters_lower_tiers(self):
        urls = [
            "https://toronto.ca/council",         # tier 1 — pass
            "https://legistar.com/toronto",       # tier 2 — pass
            "https://www.nytimes.com/news",       # tier 3 — blocked at min_tier=2
            "https://www.example.com/other",      # tier 4 — blocked at min_tier=2
        ]
        result = filter_sources(urls, min_tier=2)
        tiers = [r["tier"] for r in result]
        assert all(t <= 2 for t in tiers)
        assert any(r["url"] == "https://toronto.ca/council" for r in result)

    def test_empty_input_returns_empty(self):
        assert filter_sources([]) == []

    def test_all_blocked_returns_empty(self):
        urls = ["https://twitter.com/a", "https://reddit.com/b"]
        result = filter_sources(urls)
        assert result == []

    def test_returns_list_of_score_dicts(self):
        urls = ["https://toronto.ca/council"]
        result = filter_sources(urls)
        assert len(result) == 1
        assert "tier" in result[0]
        assert "url" in result[0]
