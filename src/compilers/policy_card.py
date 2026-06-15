"""policy_card.py — Build Hugo Markdown files from validated PolicyCard objects.

Output path: content/policy/YYYY/MM/SLUG.md  (in fyf-news-site)
Slug:         kebab-case from headline, truncated to 60 chars, date-prefixed

One .md file per PolicyCard that passes the Policy Desk gate.
No .hi.md for policy cards — EN only in Phase 2.3.
"""
import re
from datetime import datetime, timezone, timedelta

from src.ai.schema import PolicyCard

IST = timezone(timedelta(hours=5, minutes=30))


def _slugify(text: str, max_len: int = 60) -> str:
    """Convert headline to a URL-safe slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text[:max_len].rstrip("-")


def _format_list(items: list[str], prefix: str = "") -> str:
    """Render a list as YAML sequence lines."""
    if not items:
        return "  []"
    lines = []
    for item in items:
        safe = item.replace('"', "'")
        lines.append(f'  - "{safe}"')
    return "\n".join(lines)


def _escape(text: str) -> str:
    """Escape double-quotes for YAML string values."""
    return text.replace('"', "'") if text else ""


def build_policy_card(card: PolicyCard, run_dt: datetime) -> dict[str, str]:
    """Build one Hugo Markdown file for a PolicyCard.

    Returns: {path: content} dict ready for publisher.py.
    Skipped items (gate_action == 'Skip entirely') return empty dict.
    """
    if card.gate_action != "Policy Desk":
        return {}

    run_ist = run_dt.astimezone(IST)
    year  = run_ist.strftime("%Y")
    month = run_ist.strftime("%m")
    date_prefix = run_ist.strftime("%Y%m%d%H%M")
    slug = f"{date_prefix}-{_slugify(card.headline)}"
    path = f"content/policy/{year}/{month}/{slug}.md"

    # Display timestamp
    display_date = run_ist.strftime("%d %b %Y, %I:%M %p IST")

    # Persona display labels
    persona_labels = {
        "retail":         "Retail Investor",
        "fund_manager":   "Fund Manager",
        "hni":            "HNI / Family Office",
        "business_owner": "Business Owner",
        "psu_banker":     "PSU Banker",
    }
    personas_display = [
        persona_labels.get(p, p) for p in (card.personas_affected or [])
    ]

    # Sector display labels (title-case the snake_case values)
    sectors_display = [
        s.replace("_", " ").title() for s in (card.sectors_affected or [])
    ]

    # Build frontmatter
    fm_lines = [
        "---",
        f'title: "{_escape(card.headline)}"',
        f'date: "{run_ist.isoformat()}"',
        f'ministry: "{_escape(card.ministry)}"',
        f'decision_type: "{_escape(card.decision_type)}"',
        f'horizon: "{_escape(card.horizon)}"',
        f'materiality_flag: {str(card.materiality_flag).lower()}',
        f'sentiment: "{card.sentiment}"',
        f'relevance_score: {card.relevance_score}',
        f'source_url: "{card.source_url}"',
        f'display_date: "{display_date}"',
        "personas_affected:",
        _format_list(personas_display),
        "sectors_affected:",
        _format_list(sectors_display),
    ]

    # Optional material fields — only written when present
    if card.materiality_reason:
        fm_lines.append(f'materiality_reason: "{_escape(card.materiality_reason)}"')
    if card.market_lens:
        fm_lines.append(f'market_lens: "{_escape(card.market_lens)}"')

    fm_lines.append("---")

    # Body — minimal; Hugo template renders the card UI from frontmatter
    body_lines = [
        "",
        f"> **{_escape(card.what_it_means)}**",
        "",
        f"[Read full release \u2197]({card.source_url})",
        "",
    ]

    content = "\n".join(fm_lines) + "\n" + "\n".join(body_lines)
    return {path: content}


def build_policy_section_index(run_dt: datetime) -> dict[str, str]:
    """Ensure Hugo section index files exist for /policy/.
    Safe to call on every run — will not overwrite existing content.
    """
    files = {}
    run_ist = run_dt.astimezone(IST)
    year  = run_ist.strftime("%Y")
    month = run_ist.strftime("%m")

    # EN section index
    en_index_path = f"content/policy/{year}/{month}/_index.md"
    en_index = (
        "---\n"
        f'title: "Policy Desk"\n'
        f'date: "{run_ist.isoformat()}"\n'
        "layout: \"policy-list\"\n"
        "---\n"
    )
    files[en_index_path] = en_index
    return files
