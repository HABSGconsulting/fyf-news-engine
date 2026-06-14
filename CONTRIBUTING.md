# Contributing to fyf-news-engine

> This is a live pipeline. Every push to `main` is a deploy. Six cron jobs run against `main` every day.
>
> Read this before touching any code.

---

## Rule 1: Schema changes are atomic

`src/ai/schema.py` is the contract between Gemini, the pipeline, and the compilers. Every file that imports from it is a consumer. **When the contract changes, every consumer changes in the same commit.**

Before committing any schema change, run:

```bash
grep -r "from src.ai.schema import" src/
```

Every file in that output must be reviewed and, if affected, updated. Do not split schema changes across multiple commits. Do not commit `schema.py` and say "I'll fix the consumers next."

### The consumer map (update this if you add a new consumer)

| File | What it uses from schema |
|------|--------------------------|
| `src/main.py` | `RunOutput`, `ImpactPost`, `MoreReadsItem`, `EvaluatedItem` |
| `src/ai/gemini_client.py` | `RunOutput` (response model) |
| `src/compilers/news_card.py` | `ImpactPost`, `ImpactContent` |
| `src/compilers/more_reads.py` | `MoreReadsItem` |
| `src/compilers/blog_post.py` | `ImpactPost` |
| `src/learn/matcher.py` | `ImpactPost` |

---

## Rule 2: Never push breaking changes directly to `main`

`main` is what the cron job runs. There is no staging environment on the pipeline itself — `main` is production.

**Workflow for any non-trivial change:**

```
feature/your-change branch
  → test locally with: python -m src.main --dry-run
  → open a PR
  → review the diff as a whole
  → merge to main
```

This applies even if you are the only developer. The PR step forces you to look at the entire diff before it goes live. A two-minute review has saved multiple broken runs.

**What counts as "non-trivial":**
- Any change to `schema.py`
- Any change to `gemini_client.py`
- Any change to `main.py`
- Any change to a compiler (`news_card.py`, `more_reads.py`, `blog_post.py`)
- Any change to `config/settings.py` constants that affect gating logic

**What is safe to push directly to `main`:**
- Prompt text changes in `src/ai/prompts/` (text only, no code)
- `config/mappings.py` label additions (new enum value + label, nothing removed)
- README, documentation
- Log/data file changes committed by the pipeline itself

---

## Rule 3: Fail loudly, not silently

The pipeline must always write a log entry before it dies. A run that crashes without a log commit is invisible — the cron shows green and nothing happened.

**Pattern to follow in `main.py`:**

```python
try:
    result = run_pipeline()
except Exception as e:
    write_log({"status": "error", "error": str(e), "traceback": ...})
    commit_log("[skip ci] pipeline error — see run_log.json")
    raise  # still exit non-zero so GitHub Actions marks the run red
```

The `|| true` on the git push step in the workflow is intentional — slow news days should not mark a run as failed. But a Python crash must always:
1. Write to `run_log.json`
2. Commit the log with `[skip ci]`
3. Exit non-zero so the Actions run shows ❌

---

## Pre-commit checklist

Before pushing any code change:

- [ ] If `schema.py` changed: all consumers updated in the same commit (see Rule 1)
- [ ] Ran `python -m src.main --dry-run` locally with no crash
- [ ] No secrets, API keys, or D1 credentials in any source file
- [ ] No hardcoded persona strings (use `persona_map.py`)
- [ ] Blog threshold is **9**, not 8
- [ ] If changing score thresholds or gate logic: updated `00-ai-context.md` in `fyf-project-docs` to match

---

## Quick local test

```bash
# Install deps
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Copy example env
cp .env.example .env
# Fill in GEMINI_API_KEY at minimum

# Dry run (no commits, no publishes)
python -m src.main --dry-run

# Check imports only (catches broken schema consumers immediately)
python -c "import src.main"
```

`python -c "import src.main"` is the fastest possible check. If schema consumers are broken, this fails in under one second without touching the Gemini API.

---

## What caused the June 2026 incident

Four commits landed on `main` in rapid succession. Each was correct in isolation:

1. `schema.py` removed `sentiment_reason` from `ImpactContent` and restructured `RunOutput`
2. `gemini_client.py` was not updated → `AttributeError` on `result.impact_posts`
3. `main.py` imported `MoreReadsItem` which was deleted from `schema.py` → `ImportError` on startup
4. `news_card.py` still called `c.sentiment_reason` → `AttributeError` on every qualifying post

All three bugs would have been caught by `python -c "import src.main"` before the first commit landed on `main`.

The fix required three separate hotfix commits while the cron was running. Three runs produced no output.
