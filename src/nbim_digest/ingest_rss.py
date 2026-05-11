from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser

from .models import Article


def fetch_rss_articles(feed_config: dict, limit_per_feed: int = 10) -> list[Article]:
    articles: list[Article] = []
    for source in feed_config.get("sources", []):
        if not source.get("enabled"):
            continue
        parsed = feedparser.parse(source["url"])
        for entry in parsed.entries[:limit_per_feed]:
            title = getattr(entry, "title", "").strip()
            link = getattr(entry, "link", "").strip()
            if not title or not link:
                continue
            articles.append(
                Article(
                    title=title,
                    url=link,
                    source=source["name"],
                    published_at=_entry_date(entry),
                    description=getattr(entry, "summary", "") or getattr(entry, "description", ""),
                    discovery_path=f"RSS feed: {source['name']}",
                    discovery_query=None,
                    is_demo=False,
                )
            )
    return articles


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
