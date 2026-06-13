"""main.py — FYF News Pipeline orchestrator."""
import sys
from datetime import datetime, timezone, timedelta

from src.feeds.fetcher import fetch_all_feeds
from src.feeds.dedup import filter_seen, mark_seen, write_seen_hashes
from src.ai.gemini_client import run_batch
from src.compilers.news_card import build_news_card, build_section_indexes
from src.compilers.more_reads import build_more_reads
from src.git.publisher import publish_files
from src.logs.run_log import write_run_log
from config.settings import MIN_IMPACT_POSTS_PER_RUN

IST = timezone(timedelta(hours=5, minutes=30))


def main() -> None:
    run_dt = datetime.now(IST)
    run_label = run_dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")
    print(f"\n=== FYF Pipeline run: {run_label} ===")

    print("[1/5] Fetching RSS feeds...")
    raw_items = fetch_all_feeds()
    print(f"      {len(raw_items)} raw items fetched")

    print("[2/5] Deduplicating...")
    new_items = filter_seen(raw_items)
    print(f"      {len(new_items)} new items after dedup")

    if not new_items:
        print("      Nothing new — exiting cleanly.")
        write_run_log({"status": "skipped", "posts_published": 0, "items_seen": 0})
        sys.exit(0)

    print("[3/5] Calling Gemini AI...")
    run_output = run_batch(new_items)
    if run_output is None:
        print("      Gemini returned nothing — aborting.")
        write_run_log({"status": "gemini_failed", "posts_published": 0, "items_seen": len(new_items)})
        sys.exit(1)

    posts = run_output.impact_posts
    print(f"      {len(posts)} impact posts generated")

    if len(posts) < MIN_IMPACT_POSTS_PER_RUN:
        print(f"      WARNING: only {len(posts)} posts — below minimum {MIN_IMPACT_POSTS_PER_RUN}")

    print("[4/5] Building Markdown + YAML files...")
    files_to_publish: dict[str, str] = {}

    files_to_publish.update(build_section_indexes(run_dt))

    for post in posts:
        files_to_publish.update(build_news_card(post, run_dt))

    if run_output.more_reads:
        mr_path, mr_content = build_more_reads(run_output.more_reads, run_dt)
        files_to_publish[mr_path] = mr_content

    print(f"      {len(files_to_publish)} files ready ({len(posts)} EN + {len(posts)} HI + indexes)")

    print("[5/5] Publishing to fyf-news-site...")
    publish_files(files_to_publish, run_label)

    # Write dedup hashes to seen_hashes.json (separate from run history)
    item_hashes = mark_seen(new_items)
    write_seen_hashes(item_hashes)

    # Write run history to run_log.json (no hashes)
    write_run_log({
        "status": "ok",
        "posts_published": len(posts),
        "items_seen": len(new_items),
    })
    print(f"\n=== Done. {len(posts)} EN + {len(posts)} HI posts published. ===")


if __name__ == "__main__":
    main()
