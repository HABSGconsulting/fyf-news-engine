# fyf-news-engine

Private pipeline engine for FundYourFreedom.

Runs six times daily via GitHub Actions. Fetches Indian financial news, filters and interprets it for retail investors using Gemini AI, and publishes structured Markdown posts to `fyf-news-site` and `fyf-blog`.

> **⚠️ `main` is production.** Every push to `main` is a live deploy. Six cron jobs run against it every day. Read [`CONTRIBUTING.md`](./CONTRIBUTING.md) before touching any code — especially `src/ai/schema.py`.

---

## Architecture

See `fyf-project-docs` repo for full design documentation.

## Quick Reference

- Pipeline: `.github/workflows/news-pipeline.yml`
- AI schema (contract): `src/ai/schema.py`
- Schema consumers: `src/main.py`, `src/ai/gemini_client.py`, `src/compilers/news_card.py`, `src/compilers/more_reads.py`
- Lookup tables: `config/mappings.py`
- Prompts: `src/ai/prompts/`
- Run logs: `data/run_log.json`

## Required GitHub Secrets

```
GEMINI_API_KEY
NEWS_SITE_DEPLOY_KEY
BLOG_DEPLOY_KEY
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN
CLOUDFLARE_D1_DATABASE_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_NAME
```

`CF_R2_*` and `GCP_CREDENTIALS_JSON` are needed for audio and comics phases (not yet built).

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
