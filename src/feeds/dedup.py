"""Deduplication against run history."""
import json
import hashlib
from datetime import datetime, timezone, timedelta
import os

RUN_LOG_PATH = "data/run_log.json"


def _item_hash(item: dict) -> str:
    """Stable hash for dedup: based on URL + title."""
    key = (item.get("url", "") + item.get("title", "")).lower().strip()
    return hashlib.md5(key.encode()).hexdigest()


def load_seen_hashes(window_hours: int = 48) -> set[str]:
    """Load hashes of items seen in last N hours from run log."""
    if not os.path.exists(RUN_LOG_PATH):
        return set()
    try:
        with open(RUN_LOG_PATH) as f:
            log = json.load(f)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        seen = set()
        for run in log.get("runs", []):
            run_time = datetime.fromisoformat(run["run_id"])
            if run_time > cutoff:
                seen.update(run.get("item_hashes", []))
        return seen
    except Exception:
        return set()


def filter_new_items(items: list[dict], window_hours: int = 48) -> tuple[list[dict], list[str]]:
    """Return (new_items, new_hashes) filtering out already-seen items."""
    seen = load_seen_hashes(window_hours)
    new_items = []
    new_hashes = []
    for item in items:
        h = _item_hash(item)
        if h not in seen:
            new_items.append(item)
            new_hashes.append(h)
    return new_items, new_hashes
