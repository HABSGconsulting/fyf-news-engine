# fyf-news-engine

Private pipeline engine for FundYourFreedom.

Runs six times daily via GitHub Actions. Fetches Indian financial news and government policy releases, filters and interprets them for retail investors using Gemini AI, and publishes structured Markdown posts to `fyf-news-site`.

> **⚠️ `main` is production.** Every push to `main` is a live deploy. Six cron jobs run against it every day. Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) before touching any code — especially `src/ai/schema.py`.

---

## Architecture

See `fyf-project-docs` repo for full design documentation.

Two parallel paths per run:
- **[A] News path** — `fetch_all_feeds` → `run_batch()` → `news_card.py` → `content/news/`
- **[B] Policy path** — `fetch_all_feeds` → `run_policy_batch()` → `policy_card.py` → `content/policy/`

Both paths share the same Cloudflare KV dedup layer (48h TTL).

## Quick Reference

- Pipeline: `.github/workflows/news-pipeline.yml`
- AI schema (contract): `src/ai/schema.py`
- Schema consumers: `src/main.py`, `src/ai/gemini_client.py`, `src/compilers/news_card.py`, `src/compilers/policy_card.py`, `src/compilers/more_reads.py`
- Prompts: `src/ai/prompts/`
- Run logs: `data/run_log.json`

## Gemini Model Configuration

| Setting | Value |
|---|---|
| Primary model | `gemini-3.5-flash` (news + policy) |
| Fallback model | `gemini-3.5-flash` (same — no lite fallback) |
| News calls | API Key 1 (`GEMINI_API_KEY`) |
| Policy calls | API Key 2 (`GEMINI_API_KEY_2`) if set, else Key 1 |
| Effective RPD | 40/day (20 per key × 2 keys) |
| Max retries | 2 per call |

Both keys must be from **Google AI Studio** (aistudio.google.com), not Google Cloud.

## Policy Dedup

- **Freshness window**: 7-day bootstrap on first run, 24-hour steady-state thereafter
- **KV dedup**: enabled for both news and policy (48h TTL) — same item will not be re-evaluated within 48 hours
- Bootstrap flag: `data/policy_bootstrapped.flag` — written after first successful policy run

## Required GitHub Secrets

```
GEMINI_API_KEY          # Google AI Studio key 1 — used for news calls
GEMINI_API_KEY_2        # Google AI Studio key 2 — used for policy calls (doubles RPD)
NEWS_SITE_DEPLOY_KEY
CF_KV_ACCOUNT_ID
CF_KV_NAMESPACE_ID
CF_KV_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
```

`CF_R2_*` secrets are needed for audio and comics phases (not yet built).

## Local Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env with GEMINI_API_KEY at minimum

# Verify all imports are intact (catches broken schema consumers in <1 second)
python -c "import src.main"

# Full dry run (no commits, no publishes)
python -m src.main --dry-run
```

## Before You Change Any Code

1. Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) — especially the schema atomicity rule
2. Run `python -c "import src.main"` after every change to `schema.py`
3. Use a feature branch for any change to `schema.py`, `gemini_client.py`, `main.py`, or compilers
