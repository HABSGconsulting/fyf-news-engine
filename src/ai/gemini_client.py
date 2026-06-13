"""Gemini API client — chunked batching, rate limit handling, retry logic."""
import os
import time
import json
import google.generativeai as genai
from pydantic import ValidationError
from src.ai.schema import RunOutput
from config.settings import (
    GEMINI_API_KEY,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    GEMINI_MAX_RETRIES,
    GEMINI_RETRY_DELAY_SEC,
)

CHUNK_SIZE = 15  # max items per Gemini call to avoid prompt truncation


def _load_prompt(filename: str) -> str:
    path = os.path.join("src", "ai", "prompts", filename)
    with open(path) as f:
        return f.read()


def _configure():
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("AQ.PASTE"):
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. "
            "Add it to GitHub Secrets (CI) or .env (local)."
        )
    genai.configure(api_key=GEMINI_API_KEY)


def _build_prompt(news_items: list[dict], min_posts: int, max_posts: int) -> str:
    """Build the per-run prompt from template + news items."""
    template = _load_prompt("per_run_prompt.txt")
    items_text = ""
    for i, item in enumerate(news_items, 1):
        items_text += f"[ITEM {i}]\n"
        items_text += f"Title: {item['title']}\n"
        items_text += f"Summary: {item['summary']}\n"
        items_text += f"Source: {item['source']}\n"
        items_text += f"URL: {item['url']}\n\n"
    return template.format(
        NEWS_ITEMS=items_text,
        MIN_POSTS=min_posts,
        MAX_POSTS=max_posts,
    )


def _call_gemini(model_name: str, system_prompt: str, user_prompt: str) -> str:
    """Single Gemini API call. Returns raw response text."""
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    response = model.generate_content(user_prompt)
    return response.text


def _run_single_batch(
    news_items: list[dict],
    system_prompt: str,
    min_posts: int,
    max_posts: int,
    save_raw_path: str | None,
    model_override: str | None,
) -> RunOutput | None:
    """Send one chunk to Gemini with retry logic. Returns RunOutput or None."""
    user_prompt = _build_prompt(news_items, min_posts, max_posts)

    for attempt in range(GEMINI_MAX_RETRIES + 1):
        if model_override:
            model_name = model_override
        else:
            model_name = PRIMARY_MODEL if attempt == 0 else FALLBACK_MODEL

        try:
            print(f"  [GEMINI] Attempt {attempt + 1} using {model_name} ({len(news_items)} items)...")
            raw = _call_gemini(model_name, system_prompt, user_prompt)

            if save_raw_path:
                os.makedirs(os.path.dirname(save_raw_path), exist_ok=True)
                with open(save_raw_path, "w") as f:
                    f.write(raw)

            validated = RunOutput.model_validate_json(raw)
            print(f"  [GEMINI] ✓ {len(validated.impact_posts)} impact posts, "
                  f"{len(validated.more_reads)} more reads")
            return validated

        except ValidationError as e:
            print(f"  [GEMINI] Validation failed on attempt {attempt + 1}: {e}")
            if attempt < GEMINI_MAX_RETRIES:
                print(f"  [GEMINI] Waiting {GEMINI_RETRY_DELAY_SEC}s before retry...")
                time.sleep(GEMINI_RETRY_DELAY_SEC)
            else:
                print("  [GEMINI] All retries exhausted for this chunk.")
                return None

        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 60
                print(f"  [GEMINI] Rate limit hit. Waiting {wait}s...")
                time.sleep(wait)
                if attempt < GEMINI_MAX_RETRIES:
                    continue
            print(f"  [GEMINI] API error on attempt {attempt + 1}: {e}")
            if attempt >= GEMINI_MAX_RETRIES:
                return None

    return None


def run_batch(
    news_items: list[dict],
    min_posts: int = 3,
    max_posts: int = 5,
    save_raw_path: str = None,
    model_override: str = None,
) -> RunOutput | None:
    """
    Send news items to Gemini in chunks of CHUNK_SIZE (default 15).
    Merges impact_posts and more_reads from all chunks.
    Returns combined RunOutput or None if all chunks fail.
    """
    _configure()
    system_prompt = _load_prompt("system_prompt.txt")

    # Split into chunks
    chunks = [news_items[i:i + CHUNK_SIZE] for i in range(0, len(news_items), CHUNK_SIZE)]
    print(f"[GEMINI] {len(news_items)} items → {len(chunks)} chunk(s) of max {CHUNK_SIZE}")

    all_impact_posts = []
    all_more_reads = []
    any_success = False

    for idx, chunk in enumerate(chunks):
        print(f"[GEMINI] Chunk {idx + 1}/{len(chunks)}...")
        # Scale min/max proportionally per chunk
        chunk_min = max(1, round(min_posts * len(chunk) / len(news_items)))
        chunk_max = max(chunk_min, round(max_posts * len(chunk) / len(news_items)))

        result = _run_single_batch(
            chunk, system_prompt, chunk_min, chunk_max,
            save_raw_path=save_raw_path if idx == 0 else None,
            model_override=model_override,
        )

        if result is not None:
            all_impact_posts.extend(result.impact_posts)
            all_more_reads.extend(result.more_reads)
            any_success = True
        else:
            print(f"[GEMINI] Chunk {idx + 1} failed — continuing with remaining chunks")

        # Brief pause between chunks to avoid rate limits
        if idx < len(chunks) - 1:
            time.sleep(3)

    if not any_success:
        print("[GEMINI] All chunks failed.")
        return None

    # Deduplicate more_reads by URL
    seen_urls: set[str] = set()
    deduped_reads = []
    for mr in all_more_reads:
        url = getattr(mr, "url", None) or mr.get("url", "") if isinstance(mr, dict) else str(mr)
        if url not in seen_urls:
            seen_urls.add(url)
            deduped_reads.append(mr)

    # Return a merged RunOutput
    merged_raw = json.dumps({
        "impact_posts": [p.model_dump() for p in all_impact_posts],
        "more_reads": [getattr(mr, 'model_dump', lambda: mr)() for mr in deduped_reads],
    })
    return RunOutput.model_validate_json(merged_raw)
