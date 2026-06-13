"""main.py — FYF News Pipeline orchestrator."""
import sys
from datetime import datetime, timezone

from src.feeds.fetcher import fetch_all_feeds
from src.feeds.dedup import filter_seen, mark_seen
from src.ai.gemini_client import call_gemini
from src.ai.schema import RunOutput
from src.compilers.news_card import build_news_card
from src.compilers.more_reads import build_more_reads
from src.git.publisher import publish_files
from src.logs.run_log import write_run_log
from config.settings import MIN_IMPACT_POSTS_PER_RUN


def main() -> None:
    run_dt = datetime.now(timezone.utc)
    run_label = run_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n=== FYF Pipeline run: {run_label} ===")

    # 1. Fetch feeds
    print("[1/5] Fetching RSS feeds...")
    raw_items = fetch_all_feeds()
    print(f"      {len(raw_items)} raw items fetched")

    # 2. Dedup
    print("[2/5] Deduplicating...")
    new_items = filter_seen(raw_items)
    print(f"      {len(new_items)} new items after dedup")

    if not new_items:
        print("      Nothing new — exiting cleanly.")
        write_run_log(run_dt, status="skipped", posts_published=0, items_seen=0)
        sys.exit(0)

    # 3. Call Gemini
    print("[3/5] Calling Gemini AI...")
    run_output: RunOutput = call_gemini(new_items, run_dt)
    posts = run_output.impact_posts
    print(f"      {len(posts)} impact posts generated")

    if len(posts) < MIN_IMPACT_POSTS_PER_RUN:
        print(f"      WARNING: only {len(posts)} posts — below minimum {MIN_IMPACT_POSTS_PER_RUN}")

    # 4. Build output files
    print("[4/5] Building Markdown + YAML files...")
    files_to_publish: dict[str, str] = {}

    for post in posts:
        path, content = build_news_card(post, run_dt)
        files_to_publish[path] = content

    if run_output.more_reads:
        mr_path, mr_content = build_more_reads(run_output.more_reads, run_dt)
        files_to_publish[mr_path] = mr_content

    print(f"      {len(files_to_publish)} files ready")

    # 5. Publish to fyf-news-site
    print("[5/5] Publishing to fyf-news-site...")
    publish_files(files_to_publish, run_label)

    # 6. Mark items as seen + write run log
    mark_seen(new_items)
    write_run_log(run_dt, status="ok", posts_published=len(posts), items_seen=len(new_items))
    print(f"\n=== Done. {len(posts)} posts published. ===")


if __name__ == "__main__":
    main()
