# Non-secret configuration constants
# Secrets (API keys) must be in .env or GitHub Secrets

# Pipeline
MAX_IMPACT_POSTS_PER_RUN = 5
MIN_IMPACT_POSTS_PER_RUN = 3
IMPACT_SCORE_BLOG_THRESHOLD = 8    # score >= this also generates a blog post
IMPACT_SCORE_PREMIUM_THRESHOLD = 7  # score >= this is paywalled
DEDUP_WINDOW_HOURS = 48
CHUNK_SIZE = 200                    # posts per index chunk file
ROLLING_WINDOW_DAYS = 90            # Hugo listing window

# Content paths in fyf-news-site
NEWS_CONTENT_PATH = "content/news"
MORE_READS_DATA_PATH = "data/more-reads"
INDEX_PATH = "static/index"
PODCAST_PATH = "static/podcast"

# Cloudflare R2 paths
R2_COMICS_PREFIX = "comics"
R2_AUDIO_PREFIX = "audio"
R2_BOOKS_PREFIX = "books"
R2_CDN_BASE = "https://assets.fundyourfreedom.in"

# Gemini
GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_MAX_RETRIES = 2
