from nbim_digest.models import Article
from nbim_digest.rule_filter import RuleFilter


def article(title: str, description: str = "", source: str = "Test Source") -> Article:
    return Article(
        title=title,
        url="https://example.com/article",
        source=source,
        published_at="2026-05-11",
        description=description,
        discovery_path="RSS feed",
        discovery_query=None,
        is_demo=False,
    )


def test_direct_oljefondet_reference_passes_with_signal():
    result = RuleFilter.default().evaluate(
        article(
            "Oljefondet kritiseres for investering",
            "Nicolai Tangen møter spørsmål om aktivt eierskap.",
        )
    )

    assert result.decision == "pass"
    assert result.score == 100
    assert "oljefondet" in result.matched_signals
    assert "Nicolai Tangen" in result.matched_signals


def test_topical_market_news_alone_is_skipped():
    result = RuleFilter.default().evaluate(
        article(
            "Federal Reserve holder renten uendret",
            "Inflation and equity markets moved after the rate decision.",
        )
    )

    assert result.decision == "skip"
    assert result.score == 0
    assert result.topic_tags == []


def test_contextual_fund_activity_without_direct_name_goes_to_pass_when_correlated():
    result = RuleFilter.default().evaluate(
        article(
            "Fondet varsler aktivt eierskap på generalforsamling",
            "Responsible investment, shareholder voting, and governance are central topics.",
        )
    )

    assert result.decision == "pass"
    assert result.score >= 100
    assert "fondet" in result.matched_signals
    assert "aktivt eierskap" in result.matched_signals
    assert "governance" in result.topic_tags


def test_bare_norges_bank_monetary_policy_is_skipped():
    result = RuleFilter.default().evaluate(
        article(
            "Norges Bank setter opp styringsrenten",
            "Sentralbanken peker på inflasjon og kronekurs.",
        )
    )

    assert result.decision == "skip"
    assert "Norges Bank" not in result.matched_signals


def test_promotional_content_overrides_direct_match():
    result = RuleFilter.default().evaluate(
        article(
            "Sponset innhold: Oljefondet og markedsutsikter",
            "Dette er annonsørinnhold om equity markets.",
        )
    )

    assert result.decision == "skip"
    assert result.exclusion_reason == "promotional"
