"""main.py — FYF News Pipeline orchestrator.

Two parallel paths per run:
  [A] News path:   fetch_all_feeds → news_items   → run_batch()        → news_card.py   → content/posts/
  [B] Policy path: fetch_all_feeds → policy_items → run_policy_batch() → policy_card.py → content/policy/

Both paths share the same dedup layer (Cloudflare KV, 48h TTL) and publisher.
Hashes are only written to KV after a successful Gemini run — failed runs
do NOT mark items as seen, so they will be retried on the next run.

Learn-links (Phase 2.2):
  After the Gemini AI step, each qualifying ImpactPost is enriched with up to
  2 relevant learn09 posts via Cloudflare Vectorize semantic search.
  Failures are silent — learn_links stays [] and the post publishes normally.

Exit policy:
  sys.exit(0) always — including Gemini failures. Transient API errors are
  logged in run_log.json but never turn the workflow red.
  sys.exit(1) only happens on unhandled Python exceptions (crash).
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
from src.learn.matcher import get_learn_links
from config.settings import NEWS_MAX_ITEMS_PER_CALL

IST = timezone(timedelta(hours=5, minutes=30))


def _normalise_source_url(url: str) -> str:
    return url.replace("PressReleaseIframePage.aspx", "PressReleasePage.aspx")


def _item_audit(post) -> dict:
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
    return {
        "title":    card.headline,
        "score":    card.relevance_score,
        "gate":     card.gate_action,
        "ministry": card.ministry,
        "horizon":  card.horizon,
        "material": card.materiality_flag,
    }


def _enrich_learn_links(qualifying: list) -> int:
    matched = 0
    for post in qualifying:
        content = post.content_en or post.content_hi
        if not content:
            continue
        links = get_learn_links(
            content.headline or "",
            list(post.concepts or []),
            post.who_affected or "",
        )
        post.learn_links = links
        if links:
            matched += 1
    return matched


def main() -> None:
    run_dt = datetime.now(IST)
    run_label = run_dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")
    print(f"\n=== FYF Pipeline run: {run_label} ===")

    # -----------------------------------------------------------------------
    # [1] FETCH
    # -----------------------------------------------------------------------
    print("[1/6] Fetching RSS feeds...")
    raw_news, raw_policy = fetch_all_feeds()
    print(f"      {len(raw_news)} news items, {len(raw_policy)} policy items fetched")

    # -----------------------------------------------------------------------
    # [2] DEDUP
    # -----------------------------------------------------------------------
    print("[2/6] Deduplicating...")
    new_news = filter_seen(raw_news)
    new_policy = filter_seen(raw_policy)
    print(f"      {len(new_news)} new news items, {len(new_policy)} new policy items after dedup")

    if len(new_news) > NEWS_MAX_ITEMS_PER_CALL:
        overflow = len(new_news) - NEWS_MAX_ITEMS_PER_CALL
        print(f"[NEWS] Capping batch to {NEWS_MAX_ITEMS_PER_CALL} items; {overflow} overflow items deferred to next run.")
        new_news = new_news[:NEWS_MAX_ITEMS_PER_CALL]

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
    news_hashes:   list[str] = []
    policy_hashes: list[str] = []
    run_log_data = {
        "status":             "ok",
        "posts_published":    0,
        "policy_published":   0,
        "items_seen":         len(new_news),
        "items_evaluated":    0,
        "items_skipped":      0,
        "more_reads":         0,
        "learn_links_matched": 0,
        "policy_seen":        len(new_policy),
        "policy_evaluated":   0,
        "policy_skipped":     0,
        "items_detail":       [],
        "policy_detail":      [],
    }

    # -----------------------------------------------------------------------
    # [3] NEWS PATH
    # -----------------------------------------------------------------------
    if new_news:
        print("[3/6] Calling Gemini (news)...")
        run_output = run_batch(new_news)
        if run_output is None:
            print("      Gemini (news) returned nothing — logging and continuing.")
            run_log_data["status"] = "gemini_failed"
        else:
            qualifying       = [p for p in run_output.evaluated_items if p.gate_action.startswith("Impact post")]
            more_reads_items = [p for p in run_output.evaluated_items if p.gate_action == "More Reads"]
            skipped          = [p for p in run_output.evaluated_items if p.gate_action == "Skip entirely"]

            run_log_data["items_evaluated"] = len(run_output.evaluated_items)
            run_log_data["items_skipped"]   = len(skipped)
            run_log_data["more_reads"]       = len(more_reads_items)
            run_log_data["items_detail"]     = [_item_audit(p) for p in run_output.evaluated_items]

            print(f"      {len(run_output.evaluated_items)} evaluated: "
                  f"{len(qualifying)} qualifying, {len(more_reads_items)} more reads, {len(skipped)} skipped")

            if qualifying:
                print("[3a]  Enriching learn_links via Vectorize...")
                matched = _enrich_learn_links(qualifying)
                run_log_data["learn_links_matched"] = matched
                print(f"      learn_links: {matched}/{len(qualifying)} posts matched")

            files_to_publish.update(build_section_indexes(run_dt))
            for post in qualifying:
                files_to_publish.update(build_news_card(post, run_dt))
            run_log_data["posts_published"] = len(qualifying)

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

            news_hashes.extend(mark_seen(new_news))
    else:
        print("[3/6] No new news items — skipping news Gemini call.")

    # -----------------------------------------------------------------------
    # [4] POLICY PATH
    # -----------------------------------------------------------------------
    if new_policy:
        print("[4/6] Calling Gemini (policy)...")
        policy_output = run_policy_batch(new_policy)
        if policy_output is None:
            print("      Gemini (policy) returned nothing — logging and continuing.")
            if run_log_data["status"] == "ok":
                run_log_data["status"] = "gemini_policy_failed"
        else:
            publishing_cards = [c for c in policy_output.evaluated_items if c.gate_action == "Policy Desk"]
            skipped_cards    = [c for c in policy_output.evaluated_items if c.gate_action == "Skip entirely"]

            run_log_data["policy_evaluated"] = len(policy_output.evaluated_items)
            run_log_data["policy_skipped"]   = len(skipped_cards)
            run_log_data["policy_detail"]    = [_policy_audit(c) for c in policy_output.evaluated_items]

            print(f"      {len(policy_output.evaluated_items)} evaluated: "
                  f"{len(publishing_cards)} publishing, {len(skipped_cards)} skipped")

            if publishing_cards:
                files_to_publish.update(build_policy_section_index(run_dt))
                for card in publishing_cards:
                    card.source_url = _normalise_source_url(card.source_url)
                    files_to_publish.update(build_policy_card(card, run_dt))
                run_log_data["policy_published"] = len(publishing_cards)

            if not is_policy_bootstrapped():
                write_bootstrap_flag()

            policy_hashes.extend(mark_seen(new_policy))
    else:
        print("[4/6] No new policy items — skipping policy Gemini call.")

    # -----------------------------------------------------------------------
    # [5] PUBLISH
    # -----------------------------------------------------------------------
    if files_to_publish:
        print(f"[5/6] Publishing {len(files_to_publish)} files to fyf-news-site...")
        publish_files(files_to_publish, run_label)
    else:
        print("[5/6] No files to publish — slow news day or Gemini unavailable.")

    # -----------------------------------------------------------------------
    # [6] DEDUP + RUN LOG
    # -----------------------------------------------------------------------
    print("[6/6] Writing dedup hashes and run log...")
    all_hashes = news_hashes + policy_hashes
    if all_hashes:
        write_seen_hashes(all_hashes)

    write_run_log(run_log_data)

    print(
        f"\n=== Done. "
        f"{run_log_data['posts_published']} news posts, "
        f"{run_log_data['policy_published']} policy cards published. "
        f"{run_log_data['more_reads']} more reads. "
        f"Status: {run_log_data['status']} ==="
    )
    # Always exit 0. Gemini failures are soft — logged but never red.
    # Only a Python crash (unhandled exception) will exit non-zero.
    sys.exit(0)


if __name__ == "__main__":
    main()
