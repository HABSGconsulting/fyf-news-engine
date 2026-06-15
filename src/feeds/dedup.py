"""Deduplication via Cloudflare KV (48h TTL per hash).

Policy items (feed_type: policy) bypass the KV check entirely —
they are always passed through as new. This is intentional:
Policy feeds are low-volume and the freshness window in fetcher.py
already acts as the primary dedup gate for policy items.
"""
import hashlib
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# Cloudflare KV REST API
_CF_ACCOUNT_ID = os.environ.get("CF_KV_ACCOUNT_ID", "")
_CF_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID", "")
_CF_API_TOKEN = os.environ.get("CF_KV_API_TOKEN", "")
_KV_BASE = "https://api.cloudflare.com/client/v4/accounts/{account}/storage/kv/namespaces/{ns}"
_TTL_SECONDS = 48 * 3600  # 48 hours — KV auto-expires keys


def _kv_available() -> bool:
    return bool(_CF_ACCOUNT_ID and _CF_NAMESPACE_ID and _CF_API_TOKEN)


def _kv_url(suffix: str = "") -> str:
    base = _KV_BASE.format(account=_CF_ACCOUNT_ID, ns=_CF_NAMESPACE_ID)
    return base + suffix


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_CF_API_TOKEN}",
        "Content-Type": "application/json",
    }


def _item_hash(item: dict) -> str:
    key = (item.get("url", "") + item.get("title", "")).lower().strip()
    return hashlib.md5(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# KV read
# ---------------------------------------------------------------------------

def _kv_key_exists(hash_val: str) -> bool:
    """Return True if the hash key exists in KV (i.e. was seen recently)."""
    url = _kv_url(f"/values/{hash_val}")
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req):
            return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


# ---------------------------------------------------------------------------
# KV write (bulk)
# ---------------------------------------------------------------------------

def _kv_write_bulk(hashes: list[str]) -> None:
    """Write all hashes to KV in one bulk PUT call with 48h expiration."""
    if not hashes:
        return
    url = _kv_url("/bulk")
    payload = [
        {"key": h, "value": "1", "expiration_ttl": _TTL_SECONDS}
        for h in hashes
    ]
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers=_headers(), method="PUT")
    with urllib.request.urlopen(req) as resp:
        resp.read()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_seen_hashes(window_hours: int = 48) -> set[str]:
    """Returns empty set — KV checks are done per-item in filter_seen."""
    return set()


def filter_seen(items: list[dict], window_hours: int = 48) -> list[dict]:
    """Return only items whose hash is NOT present in KV.

    Policy items (feed_type: policy) always pass through — freshness
    window in fetcher.py is their dedup gate.

    Falls back to allowing all items if KV secrets are missing.
    """
    if not _kv_available():
        print("[DEDUP] KV secrets not set — skipping dedup (all items pass through)")
        return items

    new_items = []
    for item in items:
        # Policy items bypass KV check entirely
        if item.get("feed_type") == "policy":
            new_items.append(item)
            continue

        h = _item_hash(item)
        try:
            if not _kv_key_exists(h):
                new_items.append(item)
        except Exception as e:
            print(f"[DEDUP] KV read error for hash {h}: {e} — treating as new")
            new_items.append(item)
    return new_items


def mark_seen(items: list[dict]) -> list[str]:
    """Return MD5 hashes for the given items. Policy items return empty list."""
    return [_item_hash(item) for item in items if item.get("feed_type") != "policy"]


def write_seen_hashes(hashes: list[str]) -> None:
    """Write hashes to Cloudflare KV with 48h TTL.

    Falls back silently if KV secrets are not configured.
    """
    if not _kv_available():
        print("[DEDUP] KV secrets not set — hashes not persisted")
        return
    try:
        _kv_write_bulk(hashes)
        print(f"[DEDUP] {len(hashes)} hashes written to KV (48h TTL)")
    except Exception as e:
        print(f"[DEDUP] KV write error: {e} — hashes not persisted (next run may re-process)")
