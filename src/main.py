"""main.py — FYF News Pipeline orchestrator.

Two parallel paths per run:
  [A] News path:   fetch_all_feeds → news_items   → run_batch()        → news_card.py   → content/posts/
  [B] Policy path: fetch_all_feeds → policy_items → run_policy_batch() → policy_card.py → content/policy/

Both paths share the same dedup layer (seen_hashes.json) and publisher.
"""
import sys
from datetime import datetime, timezone, timedelta

from src.feeds.fetcher import fetch_all_feeds, write_bootstrap_flag, is_policy_bootstrapped
from src.feeds.dedup import filter_seen, mark_seen, write_seen_hashes
from src.ai.gemini_client import run_batch, run_policy_batch
from src.compilers.news_card import build_news_card, build_section_indexes
from src.compilers.more_reads import build_more_reads
from src.compilers.policy_card import build_policy_card, build_policy_section_index
from src.git.publisher import publish_files
from src.logs.run_log import write_run_log
from src.ai.schema import MoreReadsItem, Category

IST = timezone(timedelta(hours=5, minutes=30))


def _item_audit(post) -> dict:
    """Compact audit record for one ImpactPost item."""
    content = post.content_en or post.content_hi
    title = content.headline if content else "(no headline)"
    return {
        "title":    title,
        "score":    post.editorial_impact_score,
        "gate":     post.gate_action,
        "persona":  post.primary_persona.value if post.primary_persona else None,
        "category": post.category.value if post.category else None,
    }


def _policy_audit(card) -> dict:
    """Compact audit record for one PolicyCard item."""
    return {
        "title":    card.headline,
        "score":    card.relevance_score,
        "gate":     card.gate_action,
        "ministry": card.ministry,
        "horizon":  card.horizon,
        "material": card.materiality_flag,
    }


def main() -> None:
    run_dt = datetime.now(IST)
    run_label = run_dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")
    print(f"\n=== FYF Pipeline run: {run_label} ===")

    # -----------------------------------------------------------------------
    # [1] FETCH — returns (news_items, policy_items) split by feed_type
    # -----------------------------------------------------------------------
    print("[1/6] Fetching RSS feeds...")
    raw_news, raw_policy = fetch_all_feeds()
    print(f"      {len(raw_news)} news items, {len(raw_policy)} policy items fetched")

    # -----------------------------------------------------------------------
    # [2] DEDUP — shared layer for both paths
    # -----------------------------------------------------------------------
    print("[2/6] Deduplicating...")
    new_news = filter_seen(raw_news)
    new_policy = filter_seen(raw_policy)
    print(f"      {len(new_news)} new news items, {len(new_policy)} new policy items after dedup")

    all_new_items = new_news + new_policy
    if not all_new_items:
        print("      Nothing new — exiting cleanly.")
        write_run_log({
            "status": "skipped",
            "posts_published": 0, "policy_published": 0,
            "items_seen": 0, "items_skipped": 0, "more_reads": 0,
        })
        sys.exit(0)

    files_to_publish: dict[str, str] = {}
    all_new_hashes: list[dict] = []
    run_log_data = {
        "status": "ok",
        "posts_published": 0,
        "policy_published": 0,
        "items_seen": len(new_news),
        "items_evaluated": 0,
        "items_skipped": 0,
        "more_reads": 0,
        "policy_seen": len(new_policy),
        "policy_evaluated": 0,
        "policy_skipped": 0,
        "items_detail": [],
        "policy_detail": [],
    }

    # -----------------------------------------------------------------------
    # [3] NEWS PATH — Gemini ImpactPost
    # -----------------------------------------------------------------------
    if new_news:
        print("[3/6] Calling Gemini (news)...")
        run_output = run_batch(new_news)
        if run_output is None:
            print("      Gemini (news) returned nothing.")
            run_log_data["status"] = "gemini_failed"
        else:
            qualifying = [p for p in run_output.evaluated_items if p.gate_action.startswith("Impact post")]
            more_reads_items = [p for p in run_output.evaluated_items if p.gate_action == "More Reads"]
            skipped = [p for p in run_output.evaluated_items if p.gate_action == "Skip entirely"]

            run_log_data["items_evaluated"] = len(run_output.evaluated_items)
            run_log_data["items_skipped"] = len(skipped)
            run_log_data["more_reads"] = len(more_reads_items)
            run_log_data["items_detail"] = [_item_audit(p) for p in run_output.evaluated_items]

            print(f"      {len(run_output.evaluated_items)} evaluated: "
                  f"{len(qualifying)} qualifying, {len(more_reads_items)} more reads, {len(skipped)} skipped")

            # Build section indexes
            files_to_publish.update(build_section_indexes(run_dt))

            # Build news card files
            for post in qualifying:
                files_to_publish.update(build_news_card(post, run_dt))
            run_log_data["posts_published"] = len(qualifying)

            # Build more reads
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

        all_new_hashes.extend(mark_seen(new_news))
    else:
        print("[3/6] No new news items — skipping news Gemini call.")

    # -----------------------------------------------------------------------
    # [4] POLICY PATH — Gemini PolicyCard
    # -----------------------------------------------------------------------
    if new_policy:
        print("[4/6] Calling Gemini (policy)...")
        policy_output = run_policy_batch(new_policy)
        if policy_output is None:
            print("      Gemini (policy) returned nothing.")
            run_log_data["status"] = "gemini_policy_failed"
        else:
            publishing_cards = [c for c in policy_output.evaluated_items if c.gate_action == "Policy Desk"]
            skipped_cards    = [c for c in policy_output.evaluated_items if c.gate_action == "Skip entirely"]

            run_log_data["policy_evaluated"] = len(policy_output.evaluated_items)
            run_log_data["policy_skipped"] = len(skipped_cards)
            run_log_data["policy_detail"] = [_policy_audit(c) for c in policy_output.evaluated_items]

            print(f"      {len(policy_output.evaluated_items)} evaluated: "
                  f"{len(publishing_cards)} publishing, {len(skipped_cards)} skipped")

            if publishing_cards:
                files_to_publish.update(build_policy_section_index(run_dt))
                for card in publishing_cards:
                    files_to_publish.update(build_policy_card(card, run_dt))
                run_log_data["policy_published"] = len(publishing_cards)

        # Write bootstrap flag after first successful policy run
        if not is_policy_bootstrapped():
            write_bootstrap_flag()

        all_new_hashes.extend(mark_seen(new_policy))
    else:
        print("[4/6] No new policy items — skipping policy Gemini call.")

    # -----------------------------------------------------------------------
    # [5] PUBLISH
    # -----------------------------------------------------------------------
    if files_to_publish:
        print(f"[5/6] Publishing {len(files_to_publish)} files to fyf-news-site...")
        publish_files(files_to_publish, run_label)
    else:
        print("[5/6] No files to publish — slow news day.")

    # -----------------------------------------------------------------------
    # [6] DEDUP + RUN LOG
    # -----------------------------------------------------------------------
    print("[6/6] Writing dedup hashes and run log...")
    if all_new_hashes:
        write_seen_hashes(all_new_hashes)

    write_run_log(run_log_data)

    print(
        f"\n=== Done. "
        f"{run_log_data['posts_published']} news posts, "
        f"{run_log_data['policy_published']} policy cards published. "
        f"{run_log_data['more_reads']} more reads. ==="
    )

    # Exit 1 if BOTH paths produced zero output and there were items to process
    if (
        run_log_data["posts_published"] == 0
        and run_log_data["policy_published"] == 0
        and run_log_data["more_reads"] == 0
        and (len(new_news) > 0 or len(new_policy) > 0)
        and run_log_data["status"] not in ("ok", "skipped")
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
