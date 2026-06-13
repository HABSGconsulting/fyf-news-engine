"""Deduplication against run history."""
import json
import hashlib
from datetime import datetime, timezone, timedelta
import os

SEEN_HASHES_PATH = "data/seen_hashes.json"

IST = timezone(timedelta(hours=5, minutes=30))


def _item_hash(item: dict) -> str:
    key = (item.get("url", "") + item.get("title", "")).lower().strip()
    return hashlib.md5(key.encode()).hexdigest()


def load_seen_hashes(window_hours: int = 48) -> set[str]:
    """Load hashes seen within the last window_hours from seen_hashes.json."""
    if not os.path.exists(SEEN_HASHES_PATH):
        return set()
    try:
        with open(SEEN_HASHES_PATH) as f:
            data = json.load(f)
        cutoff = datetime.now(IST) - timedelta(hours=window_hours)
        seen = set()
        for entry in data.get("entries", []):
            try:
                entry_time = datetime.fromisoformat(entry["seen_at"])
                if entry_time > cutoff:
                    seen.update(entry.get("hashes", []))
            except Exception:
                continue
        return seen
    except json.JSONDecodeError as e:
        print(f"[WARN] seen_hashes.json corrupted: {e} — continuing without dedup")
        return set()
    except Exception as e:
        print(f"[WARN] Failed to load seen hashes: {e} — continuing without dedup")
        return set()


def filter_seen(items: list[dict], window_hours: int = 48) -> list[dict]:
    """Return only items not seen in the last window_hours."""
    seen = load_seen_hashes(window_hours)
    return [item for item in items if _item_hash(item) not in seen]


def mark_seen(items: list[dict]) -> list[str]:
    """Return hashes for the given items (for storing in seen_hashes.json)."""
    return [_item_hash(item) for item in items]


def write_seen_hashes(hashes: list[str]) -> None:
    """Append a new batch of hashes to seen_hashes.json, pruning entries older than 72h."""
    os.makedirs("data", exist_ok=True)
    now = datetime.now(IST)
    cutoff = now - timedelta(hours=72)

    data = {"entries": []}
    if os.path.exists(SEEN_HASHES_PATH):
        try:
            with open(SEEN_HASHES_PATH) as f:
                data = json.load(f)
        except Exception:
            data = {"entries": []}

    # Prune entries older than 72h
    data["entries"] = [
        e for e in data.get("entries", [])
        if _parse_dt(e.get("seen_at", "")) > cutoff
    ]

    # Append new batch
    if hashes:
        data["entries"].append({
            "seen_at": now.isoformat(),
            "hashes": hashes,
        })

    with open(SEEN_HASHES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _parse_dt(s: str) -> datetime:
    """Parse ISO datetime string; return epoch if unparseable."""
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
