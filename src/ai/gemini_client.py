"""Gemini API client — single-call model, retry logic.

Two entry points:
  run_batch()        — news items  → RunOutput (ImpactPost list)
  run_policy_batch() — policy items → PolicyRunOutput (PolicyCard list)

Locked decision: one Gemini call per item type per pipeline run.
No chunking. No merge. No CHUNK_SIZE.
See 00-ai-context.md § Locked Decisions #1.

Dual-key rotation: if GEMINI_API_KEY_2 is set, calls alternate between
key 1 (news) and key 2 (policy) per run — doubling effective RPD to 40/day.

SDK: google-genai (new SDK). NOT google-generativeai (deprecated, abandoned).
Retry logic:
  - 429 / RESOURCE_EXHAUSTED : wait 60s, retry same model
  - 503 / UNAVAILABLE        : wait 60s, retry; on final retry use FALLBACK_MODEL
  - Other exceptions          : wait RETRY_DELAY_SEC, retry same model
"""
import os
import re
import time
import json
import traceback
from google import genai
from google.genai import types
from pydantic import ValidationError
from src.ai.schema import RunOutput, PolicyRunOutput, PolicyCard
from config.settings import (
    GEMINI_API_KEY,
    GEMINI_API_KEY_2,
    PRIMARY_MODEL,
    FALLBACK_MODEL,
    GEMINI_MAX_RETRIES,
    GEMINI_RETRY_DELAY_SEC,
    GEMINI_503_RETRY_DELAY,
)


def _load_prompt(filename: str) -> str:
    path = os.path.join("src", "ai", "prompts", filename)
    with open(path) as f:
        return f.read()


def _get_client(use_key_2: bool = False) -> genai.Client:
    """Return a configured Gemini client using key 1 (news) or key 2 (policy)."""
    key = (GEMINI_API_KEY_2 if use_key_2 and GEMINI_API_KEY_2 else GEMINI_API_KEY)
    if not key or key.startswith("AQ.PASTE"):
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. "
            "Add it to GitHub Secrets (CI) or .env (local)."
        )
    if use_key_2 and GEMINI_API_KEY_2:
        print("  [GEMINI] Using API key 2 (policy rotation)")
    return genai.Client(api_key=key)


def _clean_pib_url(url: str) -> str:
    """Normalise a PIB URL to a clean, language-neutral, directly-openable link."""
    if "pib.gov.in" not in url:
        return url
    url = url.replace("PressReleaseIframePage.aspx", "PressReleasePage.aspx")
    match = re.search(r"PRID=(\d+)", url)
    if match:
        prid = match.group(1)
        return f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}"
    return url


def _build_prompt(news_items: list[dict]) -> str:
    """Build the per-run prompt from template + news items."""
    template = _load_prompt("per_run_prompt.txt")
    items_text = ""
    for i, item in enumerate(news_items, 1):
        items_text += f"[ITEM {i}]\n"
        items_text += f"Title: {item['title']}\n"
        items_text += f"Summary: {item['summary']}\n"
        items_text += f"Source: {item['source']}\n"
        items_text += f"URL: {item['url']}\n\n"
    return template.format(NEWS_ITEMS=items_text)


def _build_policy_prompt(policy_items: list[dict]) -> str:
    """Build the per-run policy prompt from items."""
    lines = [
        "Below are PIB / SEBI / RBI press releases from the last 24 hours (or 7 days on first run).",
        "Analyze each one and return a JSON object:",
        "",
        "{\"evaluated_items\": [ <PolicyCard>, <PolicyCard>, ... ]}",
        "",
        "Return one PolicyCard object per input item, in the same order.",
        "Do NOT skip items. If an item is fluff or has no real decision, set relevance_score to 1 or 2 and gate_action to empty string.",
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


def _call_gemini(client: genai.Client, model_name: str, system_prompt: str, user_prompt: str) -> str:
    """Single Gemini API call. Returns raw response text."""
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


def run_batch(
    news_items: list[dict],
    save_raw_path: str = None,
    model_override: str = None,
) -> RunOutput | None:
    """
    Send all new news items to Gemini in a single call.
    Returns RunOutput (with evaluated_items list) or None if all retries fail.
    Uses API key 1 (news calls).
    On final retry after 503s, automatically switches to FALLBACK_MODEL.
    """
    client = _get_client(use_key_2=False)
    system_prompt = _load_prompt("system_prompt.txt")
    user_prompt = _build_prompt(news_items)

    print(f"[GEMINI] News batch — {len(news_items)} items")

    for attempt in range(GEMINI_MAX_RETRIES + 1):
        # On final attempt after repeated 503s, try fallback model
        is_last_attempt = attempt == GEMINI_MAX_RETRIES
        model_name = model_override or (FALLBACK_MODEL if is_last_attempt else PRIMARY_MODEL)

        try:
            print(f"  [GEMINI] Attempt {attempt + 1} using {model_name}...")
            raw = _call_gemini(client, model_name, system_prompt, user_prompt)

            if save_raw_path:
                os.makedirs(os.path.dirname(save_raw_path), exist_ok=True)
                with open(save_raw_path, "w") as f:
                    f.write(raw)

            result = RunOutput.model_validate_json(raw)

            qualifying = [p for p in result.evaluated_items if p.gate_action.startswith("Impact post")]
            more_reads = [p for p in result.evaluated_items if p.gate_action == "More Reads"]
            skipped    = [p for p in result.evaluated_items if p.gate_action == "Skip entirely"]
            print(
                f"  [GEMINI] ✓ {len(result.evaluated_items)} evaluated: "
                f"{len(qualifying)} qualifying, {len(more_reads)} more reads, {len(skipped)} skipped"
            )
            return result

        except ValidationError as e:
            print(f"  [GEMINI] Validation failed on attempt {attempt + 1}: {e}")
            if attempt < GEMINI_MAX_RETRIES:
                print(f"  [GEMINI] Waiting {GEMINI_RETRY_DELAY_SEC}s before retry...")
                time.sleep(GEMINI_RETRY_DELAY_SEC)
                continue
            print("  [GEMINI] All retries exhausted (ValidationError).")
            return None

        except Exception as e:
            err_str = str(e)
            if _is_429(err_str):
                print(f"  [GEMINI] Rate limit (429). Waiting 60s...")
                time.sleep(60)
                if attempt < GEMINI_MAX_RETRIES:
                    continue
            elif _is_503(err_str):
                print(f"  [GEMINI] Server overload (503). Waiting {GEMINI_503_RETRY_DELAY}s...")
                time.sleep(GEMINI_503_RETRY_DELAY)
                if attempt < GEMINI_MAX_RETRIES:
                    continue
            else:
                print(f"  [GEMINI] API error on attempt {attempt + 1}: {e}")
                print(traceback.format_exc())
                if attempt < GEMINI_MAX_RETRIES:
                    print(f"  [GEMINI] Waiting {GEMINI_RETRY_DELAY_SEC}s before retry...")
                    time.sleep(GEMINI_RETRY_DELAY_SEC)
                    continue
            print("  [GEMINI] All retries exhausted (Exception).")
            return None

    return None


def run_policy_batch(
    policy_items: list[dict],
    save_raw_path: str = None,
    model_override: str = None,
) -> PolicyRunOutput | None:
    """
    Send all new policy items to Gemini using the PolicyCard schema.
    Returns PolicyRunOutput or None if all retries fail.
    Uses API key 2 if available (policy calls) — separates RPD quota from news.
    On final retry after repeated 503s, automatically switches to FALLBACK_MODEL.
    """
    client = _get_client(use_key_2=True)
    system_prompt = _load_prompt("policy_system_prompt.txt")
    user_prompt = _build_policy_prompt(policy_items)

    print(f"[GEMINI] Policy batch — {len(policy_items)} items")

    for attempt in range(GEMINI_MAX_RETRIES + 1):
        is_last_attempt = attempt == GEMINI_MAX_RETRIES
        model_name = model_override or (FALLBACK_MODEL if is_last_attempt else PRIMARY_MODEL)

        try:
            print(f"  [GEMINI-POLICY] Attempt {attempt + 1} using {model_name}...")
            raw = _call_gemini(client, model_name, system_prompt, user_prompt)

            if save_raw_path:
                os.makedirs(os.path.dirname(save_raw_path), exist_ok=True)
                with open(save_raw_path, "w") as f:
                    f.write(raw)

            result = PolicyRunOutput.model_validate_json(raw)

            for i, card in enumerate(result.evaluated_items):
                if i < len(policy_items):
                    rss_url = policy_items[i].get("url", "") or ""
                    if rss_url and rss_url.startswith("http"):
                        card.source_url = _clean_pib_url(rss_url)

            publishing = [c for c in result.evaluated_items if c.gate_action == "Policy Desk"]
            skipped    = [c for c in result.evaluated_items if c.gate_action == "Skip entirely"]
            print(
                f"  [GEMINI-POLICY] ✓ {len(result.evaluated_items)} evaluated: "
                f"{len(publishing)} publishing, {len(skipped)} skipped"
            )
            return result

        except ValidationError as e:
            print(f"  [GEMINI-POLICY] Validation failed on attempt {attempt + 1}: {e}")
            if attempt < GEMINI_MAX_RETRIES:
                print(f"  [GEMINI-POLICY] Waiting {GEMINI_RETRY_DELAY_SEC}s before retry...")
                time.sleep(GEMINI_RETRY_DELAY_SEC)
                continue
            print("  [GEMINI-POLICY] All retries exhausted (ValidationError).")
            return None

        except Exception as e:
            err_str = str(e)
            if _is_429(err_str):
                print(f"  [GEMINI-POLICY] Rate limit (429). Waiting 60s...")
                time.sleep(60)
                if attempt < GEMINI_MAX_RETRIES:
                    continue
            elif _is_503(err_str):
                print(f"  [GEMINI-POLICY] Server overload (503). Waiting {GEMINI_503_RETRY_DELAY}s...")
                time.sleep(GEMINI_503_RETRY_DELAY)
                if attempt < GEMINI_MAX_RETRIES:
                    continue
            else:
                print(f"  [GEMINI-POLICY] API error on attempt {attempt + 1}: {e}")
                print(traceback.format_exc())
                if attempt < GEMINI_MAX_RETRIES:
                    print(f"  [GEMINI-POLICY] Waiting {GEMINI_RETRY_DELAY_SEC}s before retry...")
                    time.sleep(GEMINI_RETRY_DELAY_SEC)
                    continue
            print("  [GEMINI-POLICY] All retries exhausted (Exception).")
            return None

    return None
