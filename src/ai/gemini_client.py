"""Gemini API client — two-pass model.

Pass 1 — Score (run_score_pass):
  Sends all news items (up to NEWS_MAX_ITEMS_PER_CALL) to Gemini.
  Returns only scores + classification. Output ~150 tokens. Zero truncation risk.

Pass 2 — Content (run_content_pass):
  Sends qualifying items in batches of NEWS_CONTENT_BATCH_SIZE (default 3).
  Returns full content_en, content_hi, and pro fields per item.
  Output ~2,000 tokens per batch. Well within 8,192 token limit.

Policy path (run_policy_batch) is unchanged — it works and is untouched.

Dual-key rotation: GEMINI_API_KEY used for news, GEMINI_API_KEY_2 for policy.
Exit policy: all functions return None on unrecoverable failure. Never sys.exit(1).
SDK: google-genai (new SDK). NOT google-generativeai.
"""
import os
import re
import time
import json
import traceback
from google import genai
from google.genai import types
from pydantic import ValidationError
from src.ai.schema import ScoreOutput, RunOutput, PolicyRunOutput, ImpactPost
from config.settings import (
    GEMINI_API_KEY,
    GEMINI_API_KEY_2,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    GEMINI_MAX_RETRIES,
    GEMINI_RETRY_DELAY_SEC,
    GEMINI_503_RETRY_DELAY,
    NEWS_CONTENT_BATCH_SIZE,
)


def _load_prompt(filename: str) -> str:
    path = os.path.join("src", "ai", "prompts", filename)
    with open(path) as f:
        return f.read()


def _get_client(use_key_2: bool = False) -> genai.Client:
    key = (GEMINI_API_KEY_2 if use_key_2 and GEMINI_API_KEY_2 else GEMINI_API_KEY)
    if not key or key.startswith("AQ.PASTE"):
        raise EnvironmentError("GEMINI_API_KEY is not set. Add it to GitHub Secrets.")
    if use_key_2 and GEMINI_API_KEY_2:
        print("  [GEMINI] Using API key 2 (policy rotation)")
    return genai.Client(api_key=key)


def _call_gemini(client: genai.Client, model_name: str, system_prompt: str, user_prompt: str) -> str:
    response = client.models.generate_content(
        model=model_name,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    return response.text


def _is_503(err_str: str) -> bool:
    return "503" in err_str or "UNAVAILABLE" in err_str


def _is_429(err_str: str) -> bool:
    return "429" in err_str or "RESOURCE_EXHAUSTED" in err_str


def _retry_call(client, system_prompt, user_prompt, parse_fn, tag, model_override=None):
    """
    Core retry loop for a single Gemini call.
    Returns parsed result on success, raises last exception on failure.
    """
    for attempt in range(GEMINI_MAX_RETRIES + 1):
        is_last = attempt == GEMINI_MAX_RETRIES
        model = model_override or (FALLBACK_MODEL if is_last else PRIMARY_MODEL)
        raw = None
        try:
            print(f"  [{tag}] Attempt {attempt + 1}/{GEMINI_MAX_RETRIES + 1} using {model}...")
            raw = _call_gemini(client, model, system_prompt, user_prompt)
            return parse_fn(raw)
        except ValidationError as e:
            print(f"  [{tag}] Validation error on attempt {attempt + 1}: {e.error_count()} errors")
            if raw:
                print(f"  [{tag}] Raw preview: {raw[:300]}")
            if not is_last:
                time.sleep(GEMINI_RETRY_DELAY_SEC)
                continue
            raise
        except Exception as e:
            err_str = str(e)
            if _is_429(err_str):
                print(f"  [{tag}] Rate limit (429). Waiting 60s...")
                time.sleep(60)
            elif _is_503(err_str):
                print(f"  [{tag}] Server overload (503). Waiting {GEMINI_503_RETRY_DELAY}s...")
                time.sleep(GEMINI_503_RETRY_DELAY)
            else:
                print(f"  [{tag}] API error: {e}")
                if not is_last:
                    time.sleep(GEMINI_RETRY_DELAY_SEC)
            if not is_last:
                continue
            raise


# ---------------------------------------------------------------------------
# PASS 1 — Score all news items (lightweight, zero truncation risk)
# ---------------------------------------------------------------------------

def _build_score_prompt(news_items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(news_items):
        lines.append(f"[ITEM {i}]")
        lines.append(f"Title: {item['title']}")
        lines.append(f"Summary: {item['summary']}")
        lines.append(f"Source: {item['source']}")
        lines.append("")
    return "\n".join(lines)


def run_score_pass(
    news_items: list[dict],
    model_override: str = None,
) -> ScoreOutput | None:
    """
    Pass 1: Score and classify all news items.
    Output is ~150 tokens regardless of item count. Cannot truncate.
    Returns ScoreOutput or None on failure.
    """
    client = _get_client(use_key_2=False)
    system_prompt = _load_prompt("pass1_score_prompt.txt")
    tag = "GEMINI-SCORE"
    user_prompt = _build_score_prompt(news_items)

    print(f"[{tag}] Scoring {len(news_items)} items...")
    try:
        result = _retry_call(client, system_prompt, user_prompt,
                             ScoreOutput.model_validate_json, tag, model_override)
        views    = sum(1 for s in result.scores if s.content_type.value == "view")
        skipped  = sum(1 for s in result.scores if s.gate_action == "Skip entirely")
        qualify  = sum(1 for s in result.scores if s.gate_action not in ("Skip entirely", "More Reads") and s.content_type.value != "view")
        mr       = sum(1 for s in result.scores if s.gate_action == "More Reads")
        print(f"  [{tag}] ✓ {len(result.scores)} scored: {qualify} qualify, {mr} more reads, {skipped} skip, {views} views filtered")
        return result
    except Exception as e:
        print(f"  [{tag}] Unrecoverable: {e}. Returning None.")
        return None


# ---------------------------------------------------------------------------
# PASS 2 — Generate content for qualifying items (batches of 3)
# ---------------------------------------------------------------------------

def _build_content_prompt(items_with_scores: list[dict]) -> str:
    """
    Build Pass 2 prompt. Each item includes original RSS data + Pass 1 scores.
    Gemini writes content and carries scores forward into the final ImpactPost.
    """
    lines = [
        f"Write full content for these {len(items_with_scores)} pre-scored news items.",
        "",
    ]
    for i, entry in enumerate(items_with_scores):
        item   = entry["item"]
        scores = entry["scores"]
        lines.append(f"[ITEM {i}]")
        lines.append(f"Title: {item['title']}")
        lines.append(f"Summary: {item['summary']}")
        lines.append(f"Source: {item['source']}")
        lines.append(f"URL: {item['url']}")
        lines.append(f"Scores from Pass 1:")
        lines.append(f"  reach={scores.reach_score}, immediacy={scores.immediacy_score}, "
                     f"materiality={scores.materiality_score}, surprise={scores.surprise_score}, "
                     f"actionability={scores.actionability_score}, "
                     f"total={scores.editorial_impact_score}, gate=\"{scores.gate_action}\"")
        lines.append(f"  content_type={scores.content_type.value}")
        lines.append("")
    return "\n".join(lines)


def run_content_pass(
    qualifying_items: list[dict],
    score_map: dict,
    model_override: str = None,
) -> list[ImpactPost]:
    """
    Pass 2: Generate full content for qualifying items in batches of NEWS_CONTENT_BATCH_SIZE.
    qualifying_items: list of original RSS dicts that passed the gate
    score_map: dict mapping item index (from original batch) to ScoreItem
    Returns list of ImpactPost objects (may be partial if some batches fail).
    """
    client = _get_client(use_key_2=False)
    system_prompt = _load_prompt("pass2_content_prompt.txt")
    tag = "GEMINI-CONTENT"
    batch_size = NEWS_CONTENT_BATCH_SIZE
    results: list[ImpactPost] = []

    # Build enriched list with scores attached
    enriched = [
        {"item": item, "scores": score_map[item["_pass1_index"]]}
        for item in qualifying_items
    ]

    batches = [enriched[i:i + batch_size] for i in range(0, len(enriched), batch_size)]
    print(f"[{tag}] Writing content for {len(qualifying_items)} items in {len(batches)} batch(es)...")

    for batch_num, batch in enumerate(batches, 1):
        user_prompt = _build_content_prompt(batch)
        try:
            result = _retry_call(
                client, system_prompt, user_prompt,
                RunOutput.model_validate_json, tag, model_override
            )
            print(f"  [{tag}] Batch {batch_num}/{len(batches)}: {len(result.evaluated_items)} items written")
            results.extend(result.evaluated_items)
        except Exception as e:
            print(f"  [{tag}] Batch {batch_num} failed: {e}. Skipping {len(batch)} items.")
            continue

    return results


# ---------------------------------------------------------------------------
# Policy path — unchanged
# ---------------------------------------------------------------------------

def _clean_pib_url(url: str) -> str:
    if "pib.gov.in" not in url:
        return url
    url = url.replace("PressReleaseIframePage.aspx", "PressReleasePage.aspx")
    match = re.search(r"PRID=(\d+)", url)
    if match:
        return f"https://pib.gov.in/PressReleasePage.aspx?PRID={match.group(1)}"
    return url


def _build_policy_prompt(policy_items: list[dict]) -> str:
    lines = [
        "Below are PIB / SEBI / RBI press releases. Analyze each and return a JSON object:",
        "",
        "{\"evaluated_items\": [ <PolicyCard>, <PolicyCard>, ... ]}",
        "",
        "Return one PolicyCard per input item in the same order.",
        "If an item is fluff, set relevance_score to 1 or 2.",
        "",
    ]
    for i, item in enumerate(policy_items, 1):
        lines.append(f"[ITEM {i}]")
        lines.append(f"Title: {item['title']}")
        lines.append(f"Summary: {item['summary']}")
        lines.append(f"Source: {item['source']}")
        lines.append(f"URL: {item['url']}")
        lines.append("")
    return "\n".join(lines)


def _attempt_batch(client, items, system_prompt, build_prompt_fn, parse_fn,
                   tag, model_override, save_raw_path):
    user_prompt = build_prompt_fn(items)
    for attempt in range(GEMINI_MAX_RETRIES + 1):
        is_last = attempt == GEMINI_MAX_RETRIES
        model = model_override or (FALLBACK_MODEL if is_last else PRIMARY_MODEL)
        raw = None
        try:
            print(f"  [{tag}] Attempt {attempt + 1}/{GEMINI_MAX_RETRIES + 1} using {model} ({len(items)} items)...")
            raw = _call_gemini(client, model, system_prompt, user_prompt)
            if save_raw_path:
                os.makedirs(os.path.dirname(save_raw_path), exist_ok=True)
                with open(save_raw_path, "w") as f:
                    f.write(raw)
            return parse_fn(raw)
        except ValidationError as e:
            print(f"  [{tag}] Validation error on attempt {attempt + 1}: {e.error_count()} errors")
            if raw:
                print(f"  [{tag}] Raw preview: {raw[:300]}")
            if not is_last:
                time.sleep(GEMINI_RETRY_DELAY_SEC)
                continue
            raise
        except Exception as e:
            err_str = str(e)
            if _is_429(err_str):
                print(f"  [{tag}] Rate limit (429). Waiting 60s...")
                time.sleep(60)
            elif _is_503(err_str):
                print(f"  [{tag}] Server overload (503). Waiting {GEMINI_503_RETRY_DELAY}s...")
                time.sleep(GEMINI_503_RETRY_DELAY)
            else:
                print(f"  [{tag}] API error: {e}")
                if not is_last:
                    time.sleep(GEMINI_RETRY_DELAY_SEC)
            if not is_last:
                continue
            raise


def run_policy_batch(
    policy_items: list[dict],
    save_raw_path: str = None,
    model_override: str = None,
) -> "PolicyRunOutput | None":
    client = _get_client(use_key_2=True)
    system_prompt = _load_prompt("policy_system_prompt.txt")
    tag = "GEMINI-POLICY"

    print(f"[{tag}] Policy batch — {len(policy_items)} items")

    def _parse_and_stamp(raw: str):
        result = PolicyRunOutput.model_validate_json(raw)
        for i, card in enumerate(result.evaluated_items):
            if i < len(policy_items):
                rss_url = policy_items[i].get("url", "") or ""
                if rss_url and rss_url.startswith("http"):
                    card.source_url = _clean_pib_url(rss_url)
        return result

    try:
        result = _attempt_batch(
            client, policy_items, system_prompt,
            _build_policy_prompt, _parse_and_stamp,
            tag, model_override, save_raw_path
        )
        publishing = [c for c in result.evaluated_items if c.gate_action == "Policy Desk"]
        skipped    = [c for c in result.evaluated_items if c.gate_action == "Skip entirely"]
        print(f"  [{tag}] ✓ {len(result.evaluated_items)} evaluated: {len(publishing)} publishing, {len(skipped)} skipped")
        return result
    except ValidationError:
        half = max(1, len(policy_items) // 2)
        print(f"  [{tag}] Halving to {half} items and retrying...")
        try:
            result = _attempt_batch(
                client, policy_items[:half], system_prompt,
                _build_policy_prompt, _parse_and_stamp,
                tag, model_override, save_raw_path
            )
            return result
        except Exception as e:
            print(f"  [{tag}] Halved batch failed: {e}. Returning None.")
            return None
    except Exception as e:
        print(f"  [{tag}] Unrecoverable: {e}. Returning None.")
        return None
