from pathlib import Path
import json

from .config import DATA_DIR, load_yaml
from .models import Article


def load_demo_articles(data_dir: Path = DATA_DIR) -> list[tuple[str, Article]]:
    payload = load_yaml(data_dir / "demo_articles.yaml")
    articles: list[tuple[str, Article]] = []
    for item in payload.get("articles", []):
        articles.append(
            (
                item["id"],
                Article(
                    title=item["title"],
                    url=item["url"],
                    source=item["source"],
                    published_at=str(item.get("published_at") or ""),
                    description=item.get("description", ""),
                    discovery_path=item.get("discovery_path", "Curated demo article"),
                    discovery_query=None,
                    is_demo=True,
                ),
            )
        )
    return articles


def load_demo_cached_outputs(data_dir: Path = DATA_DIR) -> dict:
    with (data_dir / "demo_cached_outputs.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)
