# fyf-news-engine

Private pipeline engine for FundYourFreedom.

Runs six times daily via GitHub Actions. Fetches Indian financial news, filters and interprets it for retail investors using Gemini AI, and publishes structured Markdown posts to `fyf-news-site` and `fyf-blog-site`.

## Architecture

See `fyf-project-docs` repo for full design documentation.

## Quick Reference

- Pipeline: `.github/workflows/news-pipeline.yml`
- AI schema: `src/ai/schema.py`
- Lookup tables: `config/mappings.py`
- Prompts: `src/ai/prompts/`
- Run logs: `data/run_log.json`

## Required GitHub Secrets

```
GEMINI_API_KEY
CF_R2_ACCESS_KEY_ID
CF_R2_SECRET_ACCESS_KEY
CF_R2_BUCKET_NAME
CF_R2_ENDPOINT_URL
NEWS_SITE_DEPLOY_KEY
BLOG_SITE_DEPLOY_KEY
```

## Local Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your API keys
python src/main.py --dry-run
```
