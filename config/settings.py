import os

# =============================================================================
# GEMINI API CONFIGURATION
# =============================================================================
# API key: reads from environment (GitHub Secret in CI, .env locally)
# The fallback string is a placeholder only — pipeline will fail fast if missing
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.PASTE_YOUR_NEW_GEMINI_KEY_HERE")

# Model selection: override via environment variable if you need to switch
#
# gemini-3.1-flash-lite : 15 RPM, 500 RPD — PRIMARY for all daily runs
#                         structured JSON + investor writing, more than sufficient
# gemini-3.5-flash      :  5 RPM,  20 RPD — WEEKLY DIGEST only (1 call/week)
#                         better for longer analytical blog posts
# gemini-3.1-pro        :  0 RPM,   0 RPD — not available on free tier
PRIMARY_MODEL       = os.environ.get("GEMINI_MODEL",         "gemini-3.1-flash-lite")
FALLBACK_MODEL      = os.environ.get("GEMINI_FALLBACK_MODEL","gemini-3.1-flash-lite")
WEEKLY_DIGEST_MODEL = os.environ.get("GEMINI_WEEKLY_MODEL",  "gemini-3.5-flash")

# Rate limit awareness
# Daily pipeline: 6 runs/day x 1 call = 6 calls  (500 RPD limit → 494 headroom)
# Weekly digest:  1 call/week                     ( 20 RPD limit → 19 headroom)
# Retry budget:   up to 2 retries per run worst case still ~18 calls/day — fine
GEMINI_CALLS_PER_RUN   = 1
GEMINI_RUNS_PER_DAY    = 6
GEMINI_DAILY_BUDGET    = 500     # 3.1-flash-lite RPD hard limit
GEMINI_RATE_LIMIT_RPM  = 15      # 3.1-flash-lite RPM hard limit
GEMINI_MAX_RETRIES     = 2
GEMINI_RETRY_DELAY_SEC = 10

# =============================================================================
# PIPELINE SETTINGS
# =============================================================================
MAX_IMPACT_POSTS_PER_RUN       = 5
MIN_IMPACT_POSTS_PER_RUN       = 3
IMPACT_SCORE_BLOG_THRESHOLD    = 8   # score >= this also generates a blog post
IMPACT_SCORE_PREMIUM_THRESHOLD = 7   # score >= this is marked premium: true
DEDUP_WINDOW_HOURS             = 48
CHUNK_SIZE                     = 200
ROLLING_WINDOW_DAYS            = 90

# =============================================================================
# CONTENT PATHS (in fyf-news-site repo)
# =============================================================================
NEWS_CONTENT_PATH    = "content/news"
MORE_READS_DATA_PATH = "data/more-reads"
INDEX_PATH           = "static/index"
PODCAST_PATH         = "static/podcast"

# =============================================================================
# CLOUDFLARE R2
# =============================================================================
CF_R2_ACCESS_KEY_ID     = os.environ.get("CF_R2_ACCESS_KEY_ID",     "")
CF_R2_SECRET_ACCESS_KEY = os.environ.get("CF_R2_SECRET_ACCESS_KEY", "")
CF_R2_BUCKET_NAME       = os.environ.get("CF_R2_BUCKET_NAME",       "fyf-assets")
CF_R2_ENDPOINT_URL      = os.environ.get("CF_R2_ENDPOINT_URL",      "")
R2_COMICS_PREFIX        = "comics"
R2_AUDIO_PREFIX         = "audio"
R2_BOOKS_PREFIX         = "books"
R2_CDN_BASE             = "https://assets.fundyourfreedom.in"

# =============================================================================
# GITHUB DEPLOY
# =============================================================================
NEWS_SITE_REPO = os.environ.get("NEWS_SITE_REPO", "HABSGconsulting/fyf-news-site")
BLOG_SITE_REPO = os.environ.get("BLOG_SITE_REPO", "HABSGconsulting/fyf-blog")
