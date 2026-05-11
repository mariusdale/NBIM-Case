from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import requests

from .config import CONFIG_DIR, load_yaml
from .models import Article


GOOGLE_NEWS_ENDPOINT = "https://news.google.com/rss/search"

TIME_HORIZON = {
    "24h": "when:1d",
    "48h": "when:2d",
    "7d": "when:7d",
}

HEADERS = {
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "User-Agent": "Mozilla/5.0",
}


def fetch_google_news_articles(
    *,
    time_horizon: str,
    config: dict | None = None,
    limit: int = 15,
) -> list[Article]:
    if time_horizon not in TIME_HORIZON:
        raise ValueError(f"Unsupported Google News time horizon: {time_horizon}")

    config = config or load_yaml(CONFIG_DIR / "google_news_rss.yaml")
    query = f"{config['query']} {TIME_HORIZON[time_horizon]}"
    response = requests.get(
        GOOGLE_NEWS_ENDPOINT,
        headers=HEADERS,
        params={
            "q": query,
            "hl": config.get("hl", "nb-NO"),
            "gl": config.get("gl", "NO"),
            "ceid": config.get("ceid", "NO:nb"),
        },
        timeout=15,
    )
    response.raise_for_status()

    parsed = feedparser.parse(response.content)
    articles: list[Article] = []
    for entry in parsed.entries[:limit]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
            continue
        articles.append(
            Article(
                title=title,
                url=link,
                source=_entry_source(entry),
                published_at=_entry_date(entry),
                description=getattr(entry, "summary", "") or getattr(entry, "description", ""),
                discovery_path=f"Google News RSS: {time_horizon}",
                discovery_query=query,
                is_demo=False,
            )
        )
    return articles


def _entry_source(entry) -> str:
    source = getattr(entry, "source", None)
    if source and getattr(source, "title", None):
        return str(source.title)
    title = getattr(entry, "title", "")
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return "Google News RSS"


def _entry_date(entry) -> str | None:
    for attr in ("published", "updated"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return parsedate_to_datetime(value).date().isoformat()
            except (TypeError, ValueError, IndexError):
                return str(value)
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6]).date().isoformat()
    return None
