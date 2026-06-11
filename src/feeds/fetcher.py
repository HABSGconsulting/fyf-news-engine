"""Fetch and normalize RSS feed items."""
import feedparser
import requests
from datetime import datetime, timezone
from typing import Optional
import yaml
import os


def load_sources(sources_path: str = "src/feeds/sources.yaml") -> list[dict]:
    with open(sources_path) as f:
        return yaml.safe_load(f)["sources"]


def fetch_feed(url: str, timeout: int = 15) -> list[dict]:
    """Fetch one RSS feed and return normalized items."""
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "FYF-NewsEngine/1.0"})
        items = []
        for entry in feed.entries:
            items.append({
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", entry.get("description", ""))[:500],
                "source": feed.feed.get("title", url),
                "published": _parse_date(entry),
            })
        return items
    except Exception as e:
        print(f"[WARN] Failed to fetch {url}: {e}")
        return []


def fetch_all(sources_path: str = "src/feeds/sources.yaml") -> list[dict]:
    """Fetch all sources and return combined deduplicated list."""
    sources = load_sources(sources_path)
    all_items = []
    for source in sources:
        items = fetch_feed(source["url"])
        print(f"[FEED] {source['name']}: {len(items)} items")
        all_items.extend(items)
    return all_items


def _parse_date(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
