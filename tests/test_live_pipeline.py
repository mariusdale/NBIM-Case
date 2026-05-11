from pathlib import Path

from nbim_digest.actions import ActionCode
from nbim_digest.models import Article, LLMRelevance, LLMReviewerAction, LLMSummaryAction
from nbim_digest.pipeline import DigestPipeline
from nbim_digest.storage import DigestStore


def test_live_pipeline_uses_google_news_with_selected_time_horizon(monkeypatch, tmp_path):
    calls = {}

    def fake_rss_articles(feed_config, limit_per_feed):
        return [
            Article(
                title="Oljefondet vurderer aktivt eierskap",
                url="https://example.com/rss",
                source="NRK Siste nyheter",
                published_at="2026-05-11",
                description="Oljefondet og governance er omtalt.",
                discovery_path="RSS feed: NRK Siste nyheter",
            )
        ]

    def fake_google_news_articles(time_horizon, config, limit):
        calls["time_horizon"] = time_horizon
        calls["limit"] = limit
        return [
            Article(
                title="Google News: NBIM og Oljefondet",
                url="https://news.google.com/rss/articles/example",
                source="E24",
                published_at="2026-05-11",
                description="NBIM og Oljefondet omtales i Google News.",
                discovery_path="Google News RSS: 7d",
                discovery_query='(NBIM OR "Norges Bank Investment Management") when:7d',
            )
        ]

    monkeypatch.setattr("nbim_digest.pipeline.fetch_rss_articles", fake_rss_articles)
    monkeypatch.setattr("nbim_digest.pipeline.fetch_google_news_articles", fake_google_news_articles)

    pipeline = DigestPipeline(
        store=DigestStore(tmp_path / "live.sqlite"),
        anthropic_api_key=None,
        data_dir=Path("data"),
        config_dir=Path("config"),
    )

    result = pipeline.run(mode="live", time_horizon="7d")

    assert calls == {"time_horizon": "7d", "limit": 15}
    assert len(result.items) == 2
    assert any(item.article.discovery_path == "Google News RSS: 7d" for item in result.items)


def test_live_pipeline_does_not_truncate_google_news_before_filtering(monkeypatch, tmp_path):
    def fake_rss_articles(feed_config, limit_per_feed):
        return [
            Article(
                title=f"Generic market item {index}",
                url=f"https://example.com/rss-{index}",
                source="NRK Siste nyheter",
                published_at="2026-05-11",
                description="Federal Reserve and inflation background without direct fund context.",
                discovery_path="RSS feed: NRK Siste nyheter",
            )
            for index in range(30)
        ]

    def fake_google_news_articles(time_horizon, config, limit):
        return [
            Article(
                title="Oljefondet får ny Google News-sak",
                url="https://news.google.com/rss/articles/important",
                source="E24",
                published_at="2026-05-11",
                description="Oljefondet omtales direkte.",
                discovery_path="Google News RSS: 24h",
                discovery_query='(NBIM OR Oljefondet) when:1d',
            )
        ]

    monkeypatch.setattr("nbim_digest.pipeline.fetch_rss_articles", fake_rss_articles)
    monkeypatch.setattr("nbim_digest.pipeline.fetch_google_news_articles", fake_google_news_articles)

    pipeline = DigestPipeline(
        store=DigestStore(tmp_path / "live.sqlite"),
        anthropic_api_key=None,
        data_dir=Path("data"),
        config_dir=Path("config"),
    )

    result = pipeline.run(mode="live", time_horizon="24h", max_articles=25)

    assert len(result.items) == 1
    assert result.items[0].article.discovery_path == "Google News RSS: 24h"


def test_live_pipeline_falls_back_when_anthropic_key_is_invalid(monkeypatch, tmp_path):
    def fake_rss_articles(feed_config, limit_per_feed):
        return []

    def fake_google_news_articles(time_horizon, config, limit):
        return [
            Article(
                title="Oljefondet får ny Google News-sak",
                url="https://news.google.com/rss/articles/important",
                source="E24",
                published_at="2026-05-11",
                description="Oljefondet omtales direkte.",
                discovery_path="Google News RSS: 24h",
                discovery_query='(NBIM OR Oljefondet) when:1d',
            )
        ]

    def fake_classify_relevance(self, article_id, article, rule, priorities):
        raise RuntimeError("Error code: 401 - invalid x-api-key")

    monkeypatch.setattr("nbim_digest.pipeline.fetch_rss_articles", fake_rss_articles)
    monkeypatch.setattr("nbim_digest.pipeline.fetch_google_news_articles", fake_google_news_articles)
    monkeypatch.setattr(
        "nbim_digest.pipeline.AnthropicDigestClient.classify_relevance",
        fake_classify_relevance,
    )

    pipeline = DigestPipeline(
        store=DigestStore(tmp_path / "live.sqlite"),
        anthropic_api_key="sk-ant-api-invalid",
        data_dir=Path("data"),
        config_dir=Path("config"),
    )

    result = pipeline.run(mode="live", time_horizon="24h")

    assert len(result.items) == 1
    assert result.items[0].reason_for_action == "Rule-based fallback used because the LLM pipeline is unavailable."
    assert "Anthropic LLM failed" in result.status_message
    assert "rule-based fallback" in result.status_message


def test_fast_review_depth_skips_adversarial_reviewer(monkeypatch, tmp_path):
    def fake_rss_articles(feed_config, limit_per_feed):
        return []

    def fake_google_news_articles(time_horizon, config, limit):
        return [
            Article(
                title="Oljefondet får ny sak",
                url="https://news.google.com/rss/articles/fast",
                source="E24",
                published_at="2026-05-11",
                description="Oljefondet omtales direkte.",
                discovery_path="Google News RSS: 24h",
                discovery_query='(NBIM OR Oljefondet) when:1d',
            )
        ]

    def fake_classify_relevance(self, article_id, article, rule, priorities):
        return LLMRelevance(score=8, include=True, reason="Direct Oil Fund mention.")

    def fake_summarize(self, article_id, article, rule, relevance, priorities):
        return LLMSummaryAction(
            summary="Short summary.",
            action=ActionCode.ALERT_COMMUNICATIONS,
            recommended_next_step="Comms should review today.",
            reason_for_action="Direct Oil Fund mention.",
        )

    def reviewer_should_not_run(self, article_id, article, rule, summary_action, priorities):
        raise AssertionError("Reviewer should be skipped in fast mode")

    monkeypatch.setattr("nbim_digest.pipeline.fetch_rss_articles", fake_rss_articles)
    monkeypatch.setattr("nbim_digest.pipeline.fetch_google_news_articles", fake_google_news_articles)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.classify_relevance", fake_classify_relevance)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.summarize_and_recommend", fake_summarize)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.review_action", reviewer_should_not_run)

    pipeline = DigestPipeline(
        store=DigestStore(tmp_path / "live.sqlite"),
        anthropic_api_key="sk-ant-api03-valid-looking",
        data_dir=Path("data"),
        config_dir=Path("config"),
    )

    result = pipeline.run(mode="live", time_horizon="24h", review_depth="fast")

    assert len(result.items) == 1
    assert result.items[0].reviewer_skipped is True
    assert result.items[0].reviewer_action == ActionCode.ALERT_COMMUNICATIONS
    assert result.items[0].final_action == ActionCode.ALERT_COMMUNICATIONS
    assert "Fast mode skipped adversarial review" in result.status_message


def test_full_review_depth_runs_adversarial_reviewer(monkeypatch, tmp_path):
    def fake_rss_articles(feed_config, limit_per_feed):
        return []

    def fake_google_news_articles(time_horizon, config, limit):
        return [
            Article(
                title="Oljefondet får ny sak",
                url="https://news.google.com/rss/articles/full",
                source="E24",
                published_at="2026-05-11",
                description="Oljefondet omtales direkte.",
                discovery_path="Google News RSS: 24h",
                discovery_query='(NBIM OR Oljefondet) when:1d',
            )
        ]

    calls = {"reviewer": 0}

    def fake_classify_relevance(self, article_id, article, rule, priorities):
        return LLMRelevance(score=8, include=True, reason="Direct Oil Fund mention.")

    def fake_summarize(self, article_id, article, rule, relevance, priorities):
        return LLMSummaryAction(
            summary="Short summary.",
            action=ActionCode.ALERT_COMMUNICATIONS,
            recommended_next_step="Comms should review today.",
            reason_for_action="Direct Oil Fund mention.",
        )

    def fake_review(self, article_id, article, rule, summary_action, priorities):
        calls["reviewer"] += 1
        return LLMReviewerAction(
            action=ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE,
            reason_for_action="Ownership review needed.",
        )

    monkeypatch.setattr("nbim_digest.pipeline.fetch_rss_articles", fake_rss_articles)
    monkeypatch.setattr("nbim_digest.pipeline.fetch_google_news_articles", fake_google_news_articles)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.classify_relevance", fake_classify_relevance)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.summarize_and_recommend", fake_summarize)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.review_action", fake_review)

    pipeline = DigestPipeline(
        store=DigestStore(tmp_path / "live.sqlite"),
        anthropic_api_key="sk-ant-api03-valid-looking",
        data_dir=Path("data"),
        config_dir=Path("config"),
    )

    result = pipeline.run(mode="live", time_horizon="24h", review_depth="full")

    assert calls["reviewer"] == 1
    assert result.items[0].reviewer_skipped is False
    assert result.items[0].reviewer_action == ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE
    assert result.items[0].final_action == ActionCode.ALERT_OWNERSHIP_AND_COMPLIANCE


def test_stream_yields_item_before_done_event(monkeypatch, tmp_path):
    def fake_rss_articles(feed_config, limit_per_feed):
        return []

    def fake_google_news_articles(time_horizon, config, limit):
        return [
            Article(
                title="Oljefondet får ny sak",
                url="https://news.google.com/rss/articles/stream",
                source="E24",
                published_at="2026-05-11",
                description="Oljefondet omtales direkte.",
                discovery_path="Google News RSS: 24h",
                discovery_query='(NBIM OR Oljefondet) when:1d',
            )
        ]

    def fake_classify_relevance(self, article_id, article, rule, priorities):
        return LLMRelevance(score=8, include=True, reason="Direct Oil Fund mention.")

    def fake_summarize(self, article_id, article, rule, relevance, priorities):
        return LLMSummaryAction(
            summary="Short summary.",
            action=ActionCode.ALERT_COMMUNICATIONS,
            recommended_next_step="Comms should review today.",
            reason_for_action="Direct Oil Fund mention.",
        )

    monkeypatch.setattr("nbim_digest.pipeline.fetch_rss_articles", fake_rss_articles)
    monkeypatch.setattr("nbim_digest.pipeline.fetch_google_news_articles", fake_google_news_articles)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.classify_relevance", fake_classify_relevance)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.summarize_and_recommend", fake_summarize)

    pipeline = DigestPipeline(
        store=DigestStore(tmp_path / "live.sqlite"),
        anthropic_api_key="sk-ant-api03-valid-looking",
        data_dir=Path("data"),
        config_dir=Path("config"),
    )

    events = list(pipeline.stream(mode="live", time_horizon="24h", review_depth="fast"))

    assert [event.kind for event in events] == ["started", "item", "done"]
    assert events[1].item is not None
    assert events[2].result is not None


def test_stream_progress_counts_only_articles_considered_by_llm(monkeypatch, tmp_path):
    def fake_rss_articles(feed_config, limit_per_feed):
        return [
            Article(
                title="Generic macro item",
                url="https://example.com/skip",
                source="NRK Siste nyheter",
                published_at="2026-05-11",
                description="Federal Reserve and inflation without Oil Fund context.",
                discovery_path="RSS feed: NRK Siste nyheter",
            )
        ]

    def fake_google_news_articles(time_horizon, config, limit):
        return [
            Article(
                title="Oljefondet får ny sak",
                url="https://news.google.com/rss/articles/stream-progress",
                source="E24",
                published_at="2026-05-11",
                description="Oljefondet omtales direkte.",
                discovery_path="Google News RSS: 24h",
                discovery_query='(NBIM OR Oljefondet) when:1d',
            )
        ]

    def fake_classify_relevance(self, article_id, article, rule, priorities):
        return LLMRelevance(score=3, include=False, reason="Not enough communications relevance.")

    monkeypatch.setattr("nbim_digest.pipeline.fetch_rss_articles", fake_rss_articles)
    monkeypatch.setattr("nbim_digest.pipeline.fetch_google_news_articles", fake_google_news_articles)
    monkeypatch.setattr("nbim_digest.pipeline.AnthropicDigestClient.classify_relevance", fake_classify_relevance)

    pipeline = DigestPipeline(
        store=DigestStore(tmp_path / "live.sqlite"),
        anthropic_api_key="sk-ant-api03-valid-looking",
        data_dir=Path("data"),
        config_dir=Path("config"),
    )

    events = list(pipeline.stream(mode="live", time_horizon="24h", review_depth="fast"))

    assert [event.kind for event in events] == ["started", "progress", "done"]
    assert events[0].candidate_count == 1
    assert events[1].processed_count == 1
    assert events[1].candidate_count == 1
    assert events[2].result is not None
    assert events[2].result.dropped_count == 2
