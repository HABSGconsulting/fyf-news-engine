"""matcher.py — Query Cloudflare Vectorize to find top-2 learn09 posts for a news item.

Called from main.py after the Gemini AI step, before news_card compile.
Returns [] on any failure — never blocks publishing.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

CF_ACCOUNT_ID     = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CF_API_TOKEN      = os.environ.get("CLOUDFLARE_API_TOKEN", "")
EMBEDDING_MODEL   = os.environ.get("CLOUDFLARE_EMBEDDING_MODEL", "@cf/baai/bge-small-en-v1.5")
VECTORIZE_INDEX   = "fyf-learn-links"
SIMILARITY_THRESHOLD = 0.75
TOP_K             = 3   # fetch 3, return best 2 after threshold filter


def _embed(text: str) -> list[float] | None:
    """Call CF Workers AI to embed a string. Returns None on failure."""
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        logger.warning("[learn_links] CF credentials not set — skipping embed")
        return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{EMBEDDING_MODEL}"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"},
            json={"text": [text]},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["result"]["data"][0]
    except Exception as e:
        logger.warning(f"[learn_links] Embed call failed: {e}")
        return None


def _query_vectorize(vector: list[float]) -> list[dict]:
    """Query Vectorize index. Returns list of match dicts (with metadata) above threshold."""
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        f"/vectorize/v2/indexes/{VECTORIZE_INDEX}/query"
    )
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"},
            json={
                "vector": vector,
                "topK": TOP_K,
                "returnMetadata": "all",
            },
            timeout=15,
        )
        resp.raise_for_status()
        matches = resp.json().get("result", {}).get("matches", [])
        return [
            m for m in matches
            if m.get("score", 0) >= SIMILARITY_THRESHOLD
        ]
    except Exception as e:
        logger.warning(f"[learn_links] Vectorize query failed: {e}")
        return []


def get_learn_links(headline: str, concepts: list[str], who_affected: str) -> list[dict]:
    """Return up to 2 learn09 posts relevant to this news item.

    Args:
        headline:     The news post headline (EN)
        concepts:     List of concept strings from ImpactPost
        who_affected: who_affected string from ImpactPost

    Returns:
        List of dicts: [{slug, title, description, difficulty}, ...], max 2 items.
        Returns [] on any failure or if no matches clear the similarity threshold.
    """
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        logger.warning("[learn_links] CF credentials missing — returning []")
        return []

    concepts_str = ", ".join(concepts) if concepts else ""
    query = (
        f"Headline: {headline}\n"
        f"Concepts: {concepts_str}\n"
        f"Who affected: {who_affected}"
    )

    vector = _embed(query)
    if vector is None:
        return []

    matches = _query_vectorize(vector)
    if not matches:
        logger.info(f"[learn_links] No matches above threshold for: {headline[:60]}")
        return []

    results = []
    for m in matches[:2]:
        meta = m.get("metadata") or {}
        slug = meta.get("slug") or m.get("id", "")
        if not slug:
            continue
        results.append({
            "slug":        slug,
            "title":       meta.get("title", ""),
            "description": meta.get("description", ""),
            "difficulty":  meta.get("difficulty", "Beginner"),
        })

    logger.info(f"[learn_links] {len(results)} link(s) matched for: {headline[:60]}")
    return results
