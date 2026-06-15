"""Fetch and normalize RSS feed items.

Freshness rules:
  feed_type: news   -> no freshness filter (same as before)
  feed_type: policy -> 7-day window on first run (no .flag file),
                       24-hour window on all subsequent runs.

Bootstrap detection: if data/policy_bootstrapped.flag does not exist,
this is the first policy run. After processing, main.py writes the flag.
"""
import feedparser
import os
from datetime import datetime, timezone, timedelta
import yaml

_BOOTSTRAP_FLAG = "data/policy_bootstrapped.flag"
_BOOTSTRAP_WINDOW_DAYS = 7
_STEADYSTATE_WINDOW_HOURS = 24


def load_sources(sources_path: str = "src/feeds/sources.yaml") -> list[dict]:
    with open(sources_path) as f:
        return yaml.safe_load(f)["sources"]


def is_policy_bootstrapped() -> bool:
    """True if the 7-day bootstrap has already run at least once."""
    return os.path.exists(_BOOTSTRAP_FLAG)


def policy_freshness_cutoff() -> datetime:
    """Returns the earliest published timestamp we will accept for policy items."""
    now = datetime.now(timezone.utc)
    if not is_policy_bootstrapped():
        print(f"[FEED] Policy bootstrap mode: accepting items from last {_BOOTSTRAP_WINDOW_DAYS} days.")
        return now - timedelta(days=_BOOTSTRAP_WINDOW_DAYS)
    return now - timedelta(hours=_STEADYSTATE_WINDOW_HOURS)


def fetch_feed(source: dict) -> list[dict]:
    """Fetch one RSS feed and return normalized items.

    For feed_type: policy, items older than the freshness cutoff are dropped here,
    before dedup and before any Gemini call.
    """
    url = source["url"]
    feed_type = source.get("feed_type", "news")

    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "FYF-NewsEngine/1.0"})
        cutoff = policy_freshness_cutoff() if feed_type == "policy" else None

        items = []
        dropped = 0
        for entry in feed.entries:
            published = _parse_date(entry)

            # Drop stale policy items before dedup + Gemini
            if cutoff and published < cutoff:
                dropped += 1
                continue

            items.append({
                "title":     entry.get("title", "").strip(),
                "url":       entry.get("link", ""),
                "summary":   entry.get("summary", entry.get("description", ""))[:500],
                "source":    feed.feed.get("title", url),
                "published": published,
                "feed_type": feed_type,
            })

        if dropped:
            print(f"[FEED] {source['name']}: {dropped} stale policy items dropped (outside freshness window).")
        return items

    except Exception as e:
        print(f"[WARN] Failed to fetch {url}: {e}")
        return []


def fetch_all_feeds(sources_path: str = "src/feeds/sources.yaml") -> tuple[list[dict], list[dict]]:
    """Fetch all sources and return (news_items, policy_items) separately.

    Splitting at fetch time so main.py can route each list to the correct
    Gemini call (ImpactPost vs PolicyCard).
    """
    sources = load_sources(sources_path)
    news_items: list[dict] = []
    policy_items: list[dict] = []

    for source in sources:
        items = fetch_feed(source)
        feed_type = source.get("feed_type", "news")
        print(f"[FEED] {source['name']} ({feed_type}): {len(items)} items")
        if feed_type == "policy":
            policy_items.extend(items)
        else:
            news_items.extend(items)

    print(f"[FEED] Total: {len(news_items)} news, {len(policy_items)} policy items")
    return news_items, policy_items


def write_bootstrap_flag() -> None:
    """Write the flag file after the first successful policy run.
    Called by main.py once policy items have been processed.
    """
    os.makedirs("data", exist_ok=True)
    with open(_BOOTSTRAP_FLAG, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())
    print("[FEED] Policy bootstrap flag written — switching to 24h steady-state from next run.")


def _parse_date(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
