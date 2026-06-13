"""Deduplication against run history."""
import json
import hashlib
from datetime import datetime, timezone, timedelta
import os

RUN_LOG_PATH = "data/run_log.json"


def _item_hash(item: dict) -> str:
    key = (item.get("url", "") + item.get("title", "")).lower().strip()
    return hashlib.md5(key.encode()).hexdigest()


def load_seen_hashes(window_hours: int = 48) -> set[str]:
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


def filter_seen(items: list[dict], window_hours: int = 48) -> list[dict]:
    """Return only items not seen in the last window_hours."""
    seen = load_seen_hashes(window_hours)
    return [item for item in items if _item_hash(item) not in seen]


def mark_seen(items: list[dict]) -> list[str]:
    """Return hashes for the given items (for storing in run log)."""
    return [_item_hash(item) for item in items]
