"""main.py — FYF News Pipeline orchestrator.

Two-pass news architecture:
  Pass 1 (run_score_pass):   Score + classify all items. ~150 tokens output. Zero truncation risk.
  Pass 2 (run_content_pass): Write content for qualifying items. 3 items/call. ~2k tokens/call.

Policy path (run_policy_batch) unchanged — single call, working.

Exit policy: sys.exit(0) always. Gemini failures logged but never turn workflow red.

Dedup policy: hashes are written only for items that were successfully processed.
  - Non-qualifying items (skip/views/more-reads) are marked seen after Pass 1.
  - Qualifying items are marked seen only after Pass 2 succeeds.
  - Items that fail Pass 2 validation are NOT marked seen — they retry next run.
"""
import sys
from datetime import datetime, timezone, timedelta

from src.feeds.fetcher import fetch_all_feeds, write_bootstrap_flag, is_policy_bootstrapped
from src.feeds.dedup import filter_seen, mark_seen, write_seen_hashes
from src.ai.gemini_client import run_score_pass, run_content_pass, run_policy_batch
from src.compilers.news_card import build_news_card, build_section_indexes
from src.compilers.more_reads import build_more_reads
from src.compilers.policy_card import build_policy_card, build_policy_section_index
from src.git.publisher import publish_files
from src.logs.run_log import write_run_log
from src.ai.schema import MoreReadsItem, Category, ImpactPost
from src.learn.matcher import get_learn_links
from config.settings import NEWS_MAX_ITEMS_PER_CALL

IST = timezone(timedelta(hours=5, minutes=30))


def _normalise_source_url(url: str) -> str:
    return url.replace("PressReleaseIframePage.aspx", "PressReleasePage.aspx")


def _item_audit(post: ImpactPost) -> dict:
    content = post.content_en or post.content_hi
    return {
        "title":        content.headline if content else "(no headline)",
        "score":        post.editorial_impact_score,
        "gate":         post.gate_action,
        "content_type": post.content_type.value,
        "persona":      post.primary_persona.value if post.primary_persona else None,
        "category":     post.category.value if post.category else None,
        "actionability": post.actionability_score,
        "behavioral_risk": post.behavioral_risk.value if post.behavioral_risk else None,
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
            content.who_affected or "",
        )
        post.learn_links = links
        if links:
            matched += 1
    return matched


def main() -> None:
    run_dt    = datetime.now(IST)
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
    new_news   = filter_seen(raw_news)
    new_policy = filter_seen(raw_policy)
    print(f"      {len(new_news)} new news items, {len(new_policy)} new policy items after dedup")

    if len(new_news) > NEWS_MAX_ITEMS_PER_CALL:
        overflow = len(new_news) - NEWS_MAX_ITEMS_PER_CALL
        print(f"[NEWS] Capping to {NEWS_MAX_ITEMS_PER_CALL} items; {overflow} deferred to next run.")
        new_news = new_news[:NEWS_MAX_ITEMS_PER_CALL]

    if not new_news and not new_policy:
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
        "status":              "ok",
        "posts_published":     0,
        "policy_published":    0,
        "items_seen":          len(new_news),
        "items_evaluated":     0,
        "items_skipped":       0,
        "views_filtered":      0,
        "more_reads":          0,
        "learn_links_matched": 0,
        "policy_seen":         len(new_policy),
        "policy_evaluated":    0,
        "policy_skipped":      0,
        "items_detail":        [],
        "policy_detail":       [],
    }

    # -----------------------------------------------------------------------
    # [3] NEWS PATH — Two-pass
    # -----------------------------------------------------------------------
    if new_news:
        for i, item in enumerate(new_news):
            item["_pass1_index"] = i

        # --- Pass 1: Score ---
        print("[3/6] Pass 1 — Scoring news items...")
        score_output = run_score_pass(new_news)

        if score_output is None:
            print("      Pass 1 failed — skipping news path.")
            run_log_data["status"] = "gemini_failed"
            # Do NOT mark any hashes — entire batch retries next run
        else:
            score_map = {s.index: s for s in score_output.scores}

            qualifying_items  = []
            non_qualifying_items = []  # skip + views + more_reads — safe to mark seen
            more_reads_scores = []
            skipped_count     = 0
            views_count       = 0

            for i, item in enumerate(new_news):
                score = score_map.get(i)
                if not score:
                    non_qualifying_items.append(item)
                    continue
                gate = score.gate_action
                ct   = score.content_type.value
                if ct == "view":
                    views_count += 1
                    non_qualifying_items.append(item)
                elif gate == "Skip entirely":
                    skipped_count += 1
                    non_qualifying_items.append(item)
                elif gate == "More Reads":
                    more_reads_scores.append((item, score))
                    non_qualifying_items.append(item)
                else:
                    qualifying_items.append(item)

            run_log_data["views_filtered"] = views_count
            run_log_data["items_skipped"]  = skipped_count
            run_log_data["more_reads"]     = len(more_reads_scores)

            # Mark non-qualifying items seen immediately — no point retrying
            news_hashes.extend(mark_seen(non_qualifying_items))

            print(f"      Pass 1 result: {len(qualifying_items)} qualify, "
                  f"{len(more_reads_scores)} more reads, {skipped_count} skip, {views_count} views filtered")

            # --- Pass 2: Content ---
            if qualifying_items:
                print("[3/6] Pass 2 — Writing content for qualifying items...")
                impact_posts = run_content_pass(qualifying_items, score_map)
                run_log_data["items_evaluated"] = len(impact_posts)
                run_log_data["items_detail"]    = [_item_audit(p) for p in impact_posts]

                print("[3a]  Enriching learn_links via Vectorize...")
                matched = _enrich_learn_links(impact_posts)
                run_log_data["learn_links_matched"] = matched

                files_to_publish.update(build_section_indexes(run_dt))
                for post in impact_posts:
                    files_to_publish.update(build_news_card(post, run_dt))
                run_log_data["posts_published"] = len(impact_posts)

                # Only mark qualifying items seen after Pass 2 succeeds
                # This ensures failed items are retried on the next run
                if impact_posts:
                    news_hashes.extend(mark_seen(qualifying_items))

            # --- More Reads ---
            if more_reads_scores:
                mr_converted = []
                for item, score in more_reads_scores:
                    title = item.get("title", "")
                    url   = item.get("url", "")
                    if title and url:
                        mr_converted.append(MoreReadsItem(
                            title=title,
                            url=url,
                            one_liner=item.get("summary", "")[:120],
                            category=Category.MACRO,
                        ))
                if mr_converted:
                    mr_path, mr_content = build_more_reads(mr_converted, run_dt)
                    files_to_publish[mr_path] = mr_content

    else:
        print("[3/6] No new news items — skipping news path.")

    # -----------------------------------------------------------------------
    # [4] POLICY PATH — unchanged
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
        print("[4/6] No new policy items — skipping policy path.")

    # -----------------------------------------------------------------------
    # [5] PUBLISH
    # -----------------------------------------------------------------------
    if files_to_publish:
        print(f"[5/6] Publishing {len(files_to_publish)} files to fyf-news-site...")
        publish_files(files_to_publish, run_label)
    else:
        print("[5/6] No files to publish.")

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
        f"{run_log_data['views_filtered']} views filtered. "
        f"Status: {run_log_data['status']} ==="
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
