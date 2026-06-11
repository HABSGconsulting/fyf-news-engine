import os

# =============================================================================
# GEMINI API CONFIGURATION
# =============================================================================
# API key: reads from environment (GitHub Secret in CI, .env locally)
# The fallback string is a placeholder only — pipeline will fail fast if missing
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.PASTE_YOUR_NEW_GEMINI_KEY_HERE")

# Model selection: override via environment variable if you need to switch
# gemini-2.5-flash-lite: 15 RPM, 500 RPD — current free tier, good for dev/early prod
# gemini-2.5-flash:      10 RPM, 500 RPD — higher quality, same daily limit
# gemini-1.5-pro:        2 RPM,  50 RPD  — highest quality, very limited free tier
PRIMARY_MODEL   = os.environ.get("GEMINI_MODEL",          "gemini-2.5-flash-lite")
FALLBACK_MODEL  = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")

# Rate limit awareness (free tier: 15 RPM, 500 RPD)
# Pipeline makes 1 Gemini call per run × 6 runs/day = 6 calls/day
# Well within 500 RPD limit. No throttling needed at current scale.
# If you scale to hourly runs (24/day), still within 500 RPD.
# If you add audio TTS via Gemini (not Google TTS), budget those calls separately.
GEMINI_CALLS_PER_RUN   = 1       # one batch call per pipeline run
GEMINI_RUNS_PER_DAY    = 6       # six scheduled runs
GEMINI_DAILY_BUDGET    = 500     # free tier hard limit (RPD)
GEMINI_RATE_LIMIT_RPM  = 15      # free tier per-minute limit
GEMINI_MAX_RETRIES     = 2       # retry once on validation failure
GEMINI_RETRY_DELAY_SEC = 10      # wait between retries (stays well under RPM)

# =============================================================================
# PIPELINE SETTINGS
# =============================================================================
MAX_IMPACT_POSTS_PER_RUN       = 5
MIN_IMPACT_POSTS_PER_RUN       = 3
IMPACT_SCORE_BLOG_THRESHOLD    = 8   # score >= this also generates a blog post
IMPACT_SCORE_PREMIUM_THRESHOLD = 7   # score >= this is marked premium: true
DEDUP_WINDOW_HOURS             = 48  # ignore items seen in last 48 hours
CHUNK_SIZE                     = 200 # posts per index chunk file
ROLLING_WINDOW_DAYS            = 90  # Hugo listing window

# =============================================================================
# CONTENT PATHS (in fyf-news-site repo)
# =============================================================================
NEWS_CONTENT_PATH   = "content/news"
MORE_READS_DATA_PATH = "data/more-reads"
INDEX_PATH          = "static/index"
PODCAST_PATH        = "static/podcast"

# =============================================================================
# CLOUDFLARE R2
# =============================================================================
CF_R2_ACCESS_KEY_ID     = os.environ.get("CF_R2_ACCESS_KEY_ID", "")
CF_R2_SECRET_ACCESS_KEY = os.environ.get("CF_R2_SECRET_ACCESS_KEY", "")
CF_R2_BUCKET_NAME       = os.environ.get("CF_R2_BUCKET_NAME", "fyf-assets")
CF_R2_ENDPOINT_URL      = os.environ.get("CF_R2_ENDPOINT_URL", "")
R2_COMICS_PREFIX        = "comics"
R2_AUDIO_PREFIX         = "audio"
R2_BOOKS_PREFIX         = "books"
R2_CDN_BASE             = "https://assets.fundyourfreedom.in"

# =============================================================================
# GITHUB DEPLOY
# =============================================================================
NEWS_SITE_REPO  = os.environ.get("NEWS_SITE_REPO",  "HABSGconsulting/fyf-news-site")
BLOG_SITE_REPO  = os.environ.get("BLOG_SITE_REPO",  "HABSGconsulting/fyf-blog")
