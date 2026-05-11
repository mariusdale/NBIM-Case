from nbim_digest.ingest_google_news import fetch_google_news_articles


class FakeResponse:
    content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Google News</title>
        <item>
          <title>Oljefondet i ny sak - E24</title>
          <link>https://news.google.com/rss/articles/example</link>
          <pubDate>Mon, 11 May 2026 08:30:00 GMT</pubDate>
          <source url="https://e24.no">E24</source>
          <description>NBIM og Oljefondet omtales.</description>
        </item>
      </channel>
    </rss>
    """

    def raise_for_status(self):
        return None


def test_google_news_fetch_uses_selected_time_horizon(monkeypatch):
    captured = {}

    def fake_get(url, headers, params, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("nbim_digest.ingest_google_news.requests.get", fake_get)

    articles = fetch_google_news_articles(time_horizon="48h")

    assert captured["url"] == "https://news.google.com/rss/search"
    assert captured["headers"]["User-Agent"] == "Mozilla/5.0"
    assert captured["headers"]["Accept"].startswith("application/rss+xml")
    assert captured["params"]["hl"] == "nb-NO"
    assert captured["params"]["gl"] == "NO"
    assert captured["params"]["ceid"] == "NO:nb"
    assert captured["params"]["q"].endswith("when:2d")
    assert articles[0].source == "E24"
    assert articles[0].discovery_path == "Google News RSS: 48h"
    assert "when:2d" in articles[0].discovery_query


def test_google_news_fetch_rejects_unknown_horizon():
    try:
        fetch_google_news_articles(time_horizon="30d")
    except ValueError as exc:
        assert "Unsupported Google News time horizon" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
