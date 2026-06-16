import os

# =============================================================================
# GEMINI API CONFIGURATION
# =============================================================================
GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY",   "AQ.PASTE_YOUR_NEW_GEMINI_KEY_HERE")
GEMINI_API_KEY_2 = os.environ.get("GEMINI_API_KEY_2", "")  # Optional second key for rotation

# Model selection
# gemini-3.5-flash : 15 RPM, 20 RPD per key — PRIMARY for all daily runs
# Dual-key rotation doubles effective RPD to 40/day across 6 runs
PRIMARY_MODEL       = os.environ.get("GEMINI_MODEL",          "gemini-3.5-flash")
FALLBACK_MODEL      = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")
WEEKLY_DIGEST_MODEL = os.environ.get("GEMINI_WEEKLY_MODEL",   "gemini-3.5-flash")

# Rate limit awareness
GEMINI_CALLS_PER_RUN   = 1
GEMINI_RUNS_PER_DAY    = 6
GEMINI_DAILY_BUDGET    = 40   # 20 RPD x 2 keys
GEMINI_RATE_LIMIT_RPM  = 15
GEMINI_MAX_RETRIES     = 2
GEMINI_RETRY_DELAY_SEC = 10

# =============================================================================
# PIPELINE SETTINGS
# =============================================================================
MAX_IMPACT_POSTS_PER_RUN       = 10
IMPACT_SCORE_BLOG_THRESHOLD    = 9
IMPACT_SCORE_PREMIUM_THRESHOLD = 7
DEDUP_WINDOW_HOURS             = 48
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
