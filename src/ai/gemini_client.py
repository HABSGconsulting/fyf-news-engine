"""Gemini API client — single-call model, retry logic.

Two entry points:
  run_batch()        — news items  → RunOutput (ImpactPost list)
  run_policy_batch() — policy items → PolicyRunOutput (PolicyCard list)

Locked decision: one Gemini call per item type per pipeline run.
No chunking. No merge. No CHUNK_SIZE.
See 00-ai-context.md § Locked Decisions #1.
"""
import os
import time
import json
import google.generativeai as genai
from pydantic import ValidationError
from src.ai.schema import RunOutput, PolicyRunOutput, PolicyCard
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


def run_batch(
    news_items: list[dict],
    save_raw_path: str = None,
    model_override: str = None,
) -> RunOutput | None:
    """
    Send all new news items to Gemini in a single call.
    Returns RunOutput (with evaluated_items list) or None if all retries fail.

    Retry policy:
      - GEMINI_MAX_RETRIES attempts total
      - Attempt 0: PRIMARY_MODEL; attempts 1+: FALLBACK_MODEL
      - ValidationError → retry (Gemini arithmetic/schema mistake)
      - 429 / RESOURCE_EXHAUSTED → 60s back-off then retry
      - Any other exception → retry up to limit, then return None
    """
    _configure()
    system_prompt = _load_prompt("system_prompt.txt")
    user_prompt = _build_prompt(news_items)

    print(f"[GEMINI] News batch — {len(news_items)} items")

    for attempt in range(GEMINI_MAX_RETRIES + 1):
        model_name = model_override or (PRIMARY_MODEL if attempt == 0 else FALLBACK_MODEL)

        try:
            print(f"  [GEMINI] Attempt {attempt + 1} using {model_name}...")
            raw = _call_gemini(model_name, system_prompt, user_prompt)

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
            else:
                print("  [GEMINI] All retries exhausted.")
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


def run_policy_batch(
    policy_items: list[dict],
    save_raw_path: str = None,
    model_override: str = None,
) -> PolicyRunOutput | None:
    """
    Send all new policy items to Gemini using the PolicyCard schema.
    Returns PolicyRunOutput or None if all retries fail.

    Same retry logic as run_batch().
    Gate action is NOT set by Gemini — the PolicyCard Pydantic validator sets it.
    """
    _configure()
    system_prompt = _load_prompt("policy_system_prompt.txt")
    user_prompt = _build_policy_prompt(policy_items)

    print(f"[GEMINI] Policy batch — {len(policy_items)} items")

    for attempt in range(GEMINI_MAX_RETRIES + 1):
        model_name = model_override or (PRIMARY_MODEL if attempt == 0 else FALLBACK_MODEL)

        try:
            print(f"  [GEMINI-POLICY] Attempt {attempt + 1} using {model_name}...")
            raw = _call_gemini(model_name, system_prompt, user_prompt)

            if save_raw_path:
                os.makedirs(os.path.dirname(save_raw_path), exist_ok=True)
                with open(save_raw_path, "w") as f:
                    f.write(raw)

            result = PolicyRunOutput.model_validate_json(raw)

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
            else:
                print("  [GEMINI-POLICY] All retries exhausted.")
                return None

        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                wait = 60
                print(f"  [GEMINI-POLICY] Rate limit hit. Waiting {wait}s...")
                time.sleep(wait)
                if attempt < GEMINI_MAX_RETRIES:
                    continue
            print(f"  [GEMINI-POLICY] API error on attempt {attempt + 1}: {e}")
            if attempt >= GEMINI_MAX_RETRIES:
                return None

    return None
