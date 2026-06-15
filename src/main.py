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
from src.ai.schema import MoreReadsItem, Category

IST = timezone(timedelta(hours=5, minutes=30))


def _item_audit(post) -> dict:
    """Compact audit record for one evaluated item — title, score, gate."""
    content = post.content_en or post.content_hi
    title = content.headline if content else "(no headline)"
    return {
        "title": title,
        "score": post.editorial_impact_score,
        "gate": post.gate_action,
        "persona": post.primary_persona.value if post.primary_persona else None,
        "category": post.category.value if post.category else None,
    }


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
        write_run_log({"status": "skipped", "posts_published": 0, "items_seen": 0, "items_skipped": 0, "more_reads": 0})
        sys.exit(0)

    print("[3/5] Calling Gemini AI...")
    run_output = run_batch(new_items)
    if run_output is None:
        print("      Gemini returned nothing — aborting.")
        write_run_log({"status": "gemini_failed", "posts_published": 0, "items_seen": len(new_items), "items_skipped": 0, "more_reads": 0})
        sys.exit(1)

    # Route items by gate_action
    qualifying = [
        p for p in run_output.evaluated_items
        if p.gate_action.startswith("Impact post")
    ]
    more_reads_items = [
        p for p in run_output.evaluated_items
        if p.gate_action == "More Reads"
    ]
    skipped = [
        p for p in run_output.evaluated_items
        if p.gate_action == "Skip entirely"
    ]

    total_evaluated = len(run_output.evaluated_items)
    print(f"      {total_evaluated} items evaluated: "
          f"{len(qualifying)} qualifying, "
          f"{len(more_reads_items)} more reads, "
          f"{len(skipped)} skipped")

    # Build audit trail — all evaluated items with title + score + gate
    items_detail = [_item_audit(p) for p in run_output.evaluated_items]

    # Slow news day — valid clean exit
    if len(qualifying) == 0:
        print("      No qualifying stories today — slow news day.")
        if more_reads_items:
            mr_converted = [
                MoreReadsItem(
                    title=p.more_reads_title or "",
                    url=p.more_reads_url or "",
                    one_liner=p.more_reads_one_liner or "",
                    category=p.category or Category.MACRO,
                )
                for p in more_reads_items
                if p.more_reads_title and p.more_reads_url
            ]
            if mr_converted:
                mr_files = {}
                mr_path, mr_content = build_more_reads(mr_converted, run_dt)
                mr_files[mr_path] = mr_content
                publish_files(mr_files, run_label)
        write_run_log({
            "status": "no_qualifying_posts",
            "posts_published": 0,
            "items_seen": len(new_items),
            "items_evaluated": total_evaluated,
            "items_skipped": len(skipped),
            "more_reads": len(more_reads_items),
            "items_detail": items_detail,
        })
        sys.exit(0)

    print("[4/5] Building Markdown + YAML files...")
    files_to_publish: dict[str, str] = {}

    files_to_publish.update(build_section_indexes(run_dt))

    for post in qualifying:
        files_to_publish.update(build_news_card(post, run_dt))

    if more_reads_items:
        mr_converted = [
            MoreReadsItem(
                title=p.more_reads_title or "",
                url=p.more_reads_url or "",
                one_liner=p.more_reads_one_liner or "",
                category=p.category or Category.MACRO,
            )
            for p in more_reads_items
            if p.more_reads_title and p.more_reads_url
        ]
        if mr_converted:
            mr_path, mr_content = build_more_reads(mr_converted, run_dt)
            files_to_publish[mr_path] = mr_content

    print(f"      {len(files_to_publish)} files ready "
          f"({len(qualifying)} EN + {len(qualifying)} HI + indexes)")

    print("[5/5] Publishing to fyf-news-site...")
    publish_files(files_to_publish, run_label)

    # Write dedup hashes
    item_hashes = mark_seen(new_items)
    write_seen_hashes(item_hashes)

    # Write run log with full audit trail
    write_run_log({
        "status": "ok",
        "posts_published": len(qualifying),
        "items_seen": len(new_items),
        "items_evaluated": total_evaluated,
        "items_skipped": len(skipped),
        "more_reads": len(more_reads_items),
        "items_detail": items_detail,
    })
    print(f"\n=== Done. {len(qualifying)} posts published. "
          f"{len(more_reads_items)} more reads. "
          f"{len(skipped)} skipped. ===")


if __name__ == "__main__":
    main()
