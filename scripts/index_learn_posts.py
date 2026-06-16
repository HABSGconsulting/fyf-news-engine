"""index_learn_posts.py — Seed / incrementally update the Cloudflare Vectorize
`fyf-learn-links` index from the learn09 corpus.

Usage (one-time seed):
    python scripts/index_learn_posts.py --content-dir /path/to/learn09/content/posts

Usage (incremental, e.g. in learn09 deploy workflow):
    python scripts/index_learn_posts.py --content-dir /path/to/learn09/content/posts --incremental

Requires env vars:
    CLOUDFLARE_ACCOUNT_ID
    CLOUDFLARE_API_TOKEN       (needs Vectorize:Edit + Workers AI:Run)
    CLOUDFLARE_EMBEDDING_MODEL (default: @cf/baai/bge-small-en-v1.5)

The learn09 content path on the exampleSite branch is:
    content/posts/
"""
import argparse
import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import frontmatter
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CF_ACCOUNT_ID   = os.environ["CLOUDFLARE_ACCOUNT_ID"]
CF_API_TOKEN    = os.environ["CLOUDFLARE_API_TOKEN"]
EMBED_MODEL     = os.environ.get("CLOUDFLARE_EMBEDDING_MODEL", "@cf/baai/bge-small-en-v1.5")
VECTORIZE_INDEX = "fyf-learn-links"
BATCH_SIZE      = 50    # vectors per upsert call
MAX_WORKERS     = 8     # concurrent embedding threads
HASH_STORE      = Path(".vectorize_hashes.json")  # local skip cache

HEADERS = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type":  "application/json",
}

# ---------------------------------------------------------------------------
# Regex extractors
# ---------------------------------------------------------------------------
NUANCE_RE = re.compile(r"\{\{<\s*nuance\s*>\}\}(.*?)\{\{<\s*/nuance\s*>\}\}", re.S)
MCQ_RE    = re.compile(r"\{\{<\s*mcq[^>]*>\}\}(.*?)\{\{<\s*/mcq\s*>\}\}", re.S)
EXPL_RE   = re.compile(r"\*\*Explanation:\*\*(.*?)(?:\*\*Note:\*\*|$)", re.S)
NOTE_RE   = re.compile(r"\*\*Note:\*\*(.*)$", re.S)


def clean_description(text: str) -> str:
    text = re.sub(r"\s*Companion read for.*$", "", text or "").strip()
    return text.rstrip(".").strip()


def extract_nuance(body: str) -> str:
    m = NUANCE_RE.search(body)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def extract_mcq_payload(body: str) -> str:
    chunks = []
    for block in MCQ_RE.findall(body):
        block = re.sub(r"\s+", " ", block).strip()
        exp  = EXPL_RE.search(block)
        note = NOTE_RE.search(block)
        if exp:  chunks.append(exp.group(1).strip())
        if note: chunks.append(note.group(1).strip())
    return " ".join(chunks).strip()


def build_embedding_payload(meta: dict, body: str) -> str:
    title       = meta.get("title", "")
    description = clean_description(meta.get("description", ""))
    nuance      = extract_nuance(body)
    mcq_text    = extract_mcq_payload(body)
    return (
        f"Title: {title}\n"
        f"Summary: {description}\n"
        f"Core Concepts: {nuance}\n"
        f"Key Questions: {mcq_text}"
    )


def build_metadata(meta: dict) -> dict:
    slug = meta.get("slug", "")
    return {
        "slug":        slug,
        "title":       meta.get("title", ""),
        "description": clean_description(meta.get("description", "")),
        "difficulty":  meta.get("difficulty", "Beginner"),
    }


# ---------------------------------------------------------------------------
# Cloudflare API helpers
# ---------------------------------------------------------------------------
def embed_text(text: str) -> list[float]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{EMBED_MODEL}"
    resp = requests.post(url, headers=HEADERS, json={"text": [text]}, timeout=20)
    resp.raise_for_status()
    return resp.json()["result"]["data"][0]


def upsert_batch(vectors: list[dict]) -> None:
    """Upsert a batch of {id, values, metadata} dicts into Vectorize."""
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
        f"/vectorize/v2/indexes/{VECTORIZE_INDEX}/upsert"
    )
    resp = requests.post(url, headers=HEADERS, json={"vectors": vectors}, timeout=30)
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Hash store for incremental skipping
# ---------------------------------------------------------------------------
def load_hashes() -> dict:
    if HASH_STORE.exists():
        return json.loads(HASH_STORE.read_text())
    return {}


def save_hashes(hashes: dict) -> None:
    HASH_STORE.write_text(json.dumps(hashes, indent=2))


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Per-file processor
# ---------------------------------------------------------------------------
def process_file(md_path: Path, stored_hashes: dict, incremental: bool) -> dict | None:
    """Parse a .md file and return a vector dict, or None if skipped."""
    h = file_hash(md_path)
    slug = md_path.stem  # filename without .md = slug

    if incremental and stored_hashes.get(slug) == h:
        return None  # unchanged — skip

    try:
        post = frontmatter.load(str(md_path))
    except Exception as e:
        logger.warning(f"Failed to parse {md_path.name}: {e}")
        return None

    meta = dict(post.metadata)
    if not meta.get("slug"):
        meta["slug"] = slug

    body    = post.content or ""
    payload = build_embedding_payload(meta, body)

    try:
        vector = embed_text(payload)
    except Exception as e:
        logger.warning(f"Embed failed for {slug}: {e}")
        return None

    return {
        "_slug": slug,
        "_hash": h,
        "vector": {
            "id":       slug,
            "values":   vector,
            "metadata": build_metadata(meta),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Index learn09 posts into Cloudflare Vectorize")
    parser.add_argument("--content-dir", required=True, help="Path to learn09 content/posts/ directory")
    parser.add_argument("--incremental", action="store_true", help="Skip files unchanged since last run")
    args = parser.parse_args()

    content_dir = Path(args.content_dir)
    md_files    = sorted(content_dir.rglob("*.md"))
    logger.info(f"Found {len(md_files)} .md files in {content_dir}")

    stored_hashes = load_hashes() if args.incremental else {}
    new_hashes    = dict(stored_hashes)

    vectors_to_upsert: list[dict] = []
    processed = skipped = failed = 0

    # Embed concurrently
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(process_file, f, stored_hashes, args.incremental): f
            for f in md_files
        }
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                skipped += 1
                continue
            if "vector" not in result:
                failed += 1
                continue
            vectors_to_upsert.append(result["vector"])
            new_hashes[result["_slug"]] = result["_hash"]
            processed += 1

            # Upsert in batches as we go
            if len(vectors_to_upsert) >= BATCH_SIZE:
                batch = vectors_to_upsert[:BATCH_SIZE]
                vectors_to_upsert = vectors_to_upsert[BATCH_SIZE:]
                try:
                    upsert_batch(batch)
                    logger.info(f"Upserted batch of {len(batch)} | total processed: {processed}")
                except Exception as e:
                    logger.error(f"Upsert batch failed: {e}")
                time.sleep(0.2)  # brief pause between batches

    # Upsert remaining
    if vectors_to_upsert:
        try:
            upsert_batch(vectors_to_upsert)
            logger.info(f"Upserted final batch of {len(vectors_to_upsert)}")
        except Exception as e:
            logger.error(f"Final upsert batch failed: {e}")

    save_hashes(new_hashes)

    logger.info(
        f"\nDone. processed={processed} skipped={skipped} failed={failed} "
        f"total_indexed={processed}"
    )


if __name__ == "__main__":
    main()
