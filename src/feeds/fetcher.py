"""Fetch and normalize RSS feed items.

Freshness rules:
  feed_type: news   -> (now - last_run_time) + 30 min buffer
                       Falls back to 2.5h if last_run.txt is missing or unreadable.
  feed_type: policy -> 7-day window on first run (no .flag file),
                       24-hour window on all subsequent runs.

Bootstrap detection: if data/policy_bootstrapped.flag does not exist,
this is the first policy run. After processing, main.py writes the flag.
"""
import feedparser
import os
from datetime import datetime, timezone, timedelta
import yaml

_BOOTSTRAP_FLAG       = "data/policy_bootstrapped.flag"
_LAST_RUN_PATH        = "data/last_run.txt"
_BOOTSTRAP_WINDOW_DAYS    = 7
_STEADYSTATE_WINDOW_HOURS = 24
_FALLBACK_NEWS_WINDOW_HRS = 2.5   # used when last_run.txt is absent
_BUFFER_MINUTES           = 30    # always added on top of gap


def load_sources(sources_path: str = "src/feeds/sources.yaml") -> list[dict]:
    with open(sources_path) as f:
        return yaml.safe_load(f)["sources"]


def is_policy_bootstrapped() -> bool:
    return os.path.exists(_BOOTSTRAP_FLAG)


def policy_freshness_cutoff() -> datetime:
    now = datetime.now(timezone.utc)
    if not is_policy_bootstrapped():
        print(f"[FEED] Policy bootstrap mode: accepting items from last {_BOOTSTRAP_WINDOW_DAYS} days.")
        return now - timedelta(days=_BOOTSTRAP_WINDOW_DAYS)
    return now - timedelta(hours=_STEADYSTATE_WINDOW_HOURS)


def news_freshness_cutoff() -> datetime:
    """Cutoff = last run time - 30 min buffer.

    Reads the ISO timestamp from the first line of data/last_run.txt.
    Falls back to now - 2.5h if the file is missing or unparseable.
    """
    now = datetime.now(timezone.utc)
    fallback = now - timedelta(hours=_FALLBACK_NEWS_WINDOW_HRS)

    if not os.path.exists(_LAST_RUN_PATH):
        print(f"[FEED] last_run.txt not found — using {_FALLBACK_NEWS_WINDOW_HRS}h fallback window.")
        return fallback

    try:
        with open(_LAST_RUN_PATH) as f:
            raw = f.readline().strip()
        last_run_dt = datetime.fromisoformat(raw)
        if last_run_dt.tzinfo is None:
            last_run_dt = last_run_dt.replace(tzinfo=timezone.utc)
        else:
            last_run_dt = last_run_dt.astimezone(timezone.utc)

        gap = now - last_run_dt
        window = gap + timedelta(minutes=_BUFFER_MINUTES)
        cutoff = now - window
        gap_mins = int(gap.total_seconds() / 60)
        window_mins = int(window.total_seconds() / 60)
        print(f"[FEED] Last run was {gap_mins}m ago — news freshness window: {window_mins}m (gap + 30m buffer).")
        return cutoff

    except Exception as e:
        print(f"[FEED] Could not parse last_run.txt ({e}) — using {_FALLBACK_NEWS_WINDOW_HRS}h fallback window.")
        return fallback


def fetch_feed(source: dict) -> list[dict]:
    """Fetch one RSS feed and return normalized items."""
    url = source["url"]
    feed_type = source.get("feed_type", "news")

    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "FYF-NewsEngine/1.0"})
        cutoff = policy_freshness_cutoff() if feed_type == "policy" else news_freshness_cutoff()

        items = []
        dropped = 0
        for entry in feed.entries:
            published = _parse_date(entry)
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
            print(f"[FEED] {source['name']}: {dropped} stale {feed_type} items dropped (outside freshness window).")
        return items

    except Exception as e:
        print(f"[WARN] Failed to fetch {url}: {e}")
        return []


def fetch_all_feeds(sources_path: str = "src/feeds/sources.yaml") -> tuple[list[dict], list[dict]]:
    """Fetch all sources and return (news_items, policy_items) separately."""
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
    os.makedirs("data", exist_ok=True)
    with open(_BOOTSTRAP_FLAG, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())
    print("[FEED] Policy bootstrap flag written — switching to 24h steady-state from next run.")


def _parse_date(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)
