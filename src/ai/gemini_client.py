"""Gemini API client with rate limit handling and retry logic."""
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
            response_mime_type="application/json",  # JSON mode
            temperature=0.3,   # low temp for consistent structured output
        ),
    )
    response = model.generate_content(user_prompt)
    return response.text


def run_batch(
    news_items: list[dict],
    min_posts: int = 3,
    max_posts: int = 5,
    save_raw_path: str = None,
) -> RunOutput | None:
    """
    Send batch of news items to Gemini. Returns validated RunOutput or None.

    Saves raw response before validation (enables replay without re-calling API).
    Retries once with fallback model on validation failure.
    """
    _configure()
    system_prompt = _load_prompt("system_prompt.txt")
    user_prompt = _build_prompt(news_items, min_posts, max_posts)

    for attempt in range(GEMINI_MAX_RETRIES + 1):
        model_name = PRIMARY_MODEL if attempt == 0 else FALLBACK_MODEL
        try:
            print(f"[GEMINI] Attempt {attempt + 1} using {model_name}...")
            raw = _call_gemini(model_name, system_prompt, user_prompt)

            # Always save raw response before validation
            if save_raw_path:
                os.makedirs(os.path.dirname(save_raw_path), exist_ok=True)
                with open(save_raw_path, "w") as f:
                    f.write(raw)

            validated = RunOutput.model_validate_json(raw)
            print(f"[GEMINI] Success: {len(validated.impact_posts)} impact posts, "
                  f"{len(validated.more_reads)} more reads")
            return validated

        except ValidationError as e:
            print(f"[GEMINI] Validation failed on attempt {attempt + 1}: {e}")
            if attempt < GEMINI_MAX_RETRIES:
                print(f"[GEMINI] Waiting {GEMINI_RETRY_DELAY_SEC}s before retry...")
                time.sleep(GEMINI_RETRY_DELAY_SEC)
            else:
                print("[GEMINI] All retries exhausted. Skipping this run.")
                return None

        except Exception as e:
            # Handle rate limit errors specifically
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 60  # wait a full minute on rate limit hit
                print(f"[GEMINI] Rate limit hit. Waiting {wait}s...")
                time.sleep(wait)
                if attempt < GEMINI_MAX_RETRIES:
                    continue
            print(f"[GEMINI] API error on attempt {attempt + 1}: {e}")
            if attempt >= GEMINI_MAX_RETRIES:
                return None

    return None
