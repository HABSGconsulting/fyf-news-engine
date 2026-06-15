"""policy_card.py — Build Hugo Markdown files from validated PolicyCard objects.

Output:
  EN:  content/policy/YYYY/MM/SLUG.md       — English frontmatter + no body
  HI:  content/policy/YYYY/MM/SLUG.hi.md    — Hindi frontmatter (translated fields)

Slug:         kebab-case from headline, truncated to 60 chars, date-prefixed.
One EN + one HI file per PolicyCard that passes the Policy Desk gate (relevance_score >= 6).
EN file uses English text fields. HI file uses *_hi translated text fields.
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.ai.schema import PolicyCard

IST = timezone(timedelta(hours=5, minutes=30))


def _slugify(text: str, max_len: int = 60) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text[:max_len].rstrip("-")


def _format_list(items: list[str]) -> str:
    if not items:
        return "  []"
    return "\n".join(f'  - "{item.replace(chr(34), chr(39))}"' for item in items)


def _escape(text: Optional[str]) -> str:
    if not text:
        return ""
    return text.replace('"', "'").replace('\n', ' ').strip()


def _build_frontmatter_en(
    card: PolicyCard,
    run_ist: datetime,
    display_date: str,
    personas_display: list[str],
    sectors_display: list[str],
) -> str:
    """Build YAML frontmatter for the English (.md) file."""
    lines = [
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
        f'context_and_trigger: "{_escape(card.context_and_trigger)}"',
        f'mechanism_of_impact: "{_escape(card.mechanism_of_impact)}"',
        f'forward_outlook: "{_escape(card.forward_outlook)}"',
        "personas_affected:",
        _format_list(personas_display),
        "sectors_affected:",
        _format_list(sectors_display),
    ]

    if card.materiality_reason:
        lines.append(f'materiality_reason: "{_escape(card.materiality_reason)}"')
    if card.market_lens:
        lines.append(f'market_lens: "{_escape(card.market_lens)}"')

    lines.append("---")
    return "\n".join(lines) + "\n"


def _build_frontmatter_hi(
    card: PolicyCard,
    run_ist: datetime,
    display_date: str,
    personas_display: list[str],
    sectors_display: list[str],
) -> str:
    """Build YAML frontmatter for the Hindi (.hi.md) file — uses *_hi translated fields."""
    lines = [
        "---",
        f'title: "{_escape(card.headline_hi or card.headline)}"',
        f'date: "{run_ist.isoformat()}"',
        f'ministry: "{_escape(card.ministry)}"',
        f'decision_type: "{_escape(card.decision_type)}"',
        f'horizon: "{_escape(card.horizon)}"',
        f'materiality_flag: {str(card.materiality_flag).lower()}',
        f'sentiment: "{card.sentiment}"',
        f'relevance_score: {card.relevance_score}',
        f'source_url: "{card.source_url}"',
        f'display_date: "{display_date}"',
        f'context_and_trigger: "{_escape(card.context_and_trigger_hi or card.context_and_trigger)}"',
        f'mechanism_of_impact: "{_escape(card.mechanism_of_impact_hi or card.mechanism_of_impact)}"',
        f'forward_outlook: "{_escape(card.forward_outlook_hi or card.forward_outlook)}"',
        "personas_affected:",
        _format_list(personas_display),
        "sectors_affected:",
        _format_list(sectors_display),
    ]

    if card.materiality_reason_hi or card.materiality_reason:
        lines.append(f'materiality_reason: "{_escape(card.materiality_reason_hi or card.materiality_reason)}"')
    if card.market_lens_hi or card.market_lens:
        lines.append(f'market_lens: "{_escape(card.market_lens_hi or card.market_lens)}"')

    lines.append("---")
    return "\n".join(lines) + "\n"


def build_policy_card(card: PolicyCard, run_dt: datetime) -> dict[str, str]:
    """Build one EN and one HI Hugo Markdown file for a PolicyCard.

    Returns: {path: content} dict with 2 entries (EN + HI).
    Skipped items (gate_action != 'Policy Desk') return empty dict.
    """
    if card.gate_action != "Policy Desk":
        return {}

    run_ist      = run_dt.astimezone(IST)
    year         = run_ist.strftime("%Y")
    month        = run_ist.strftime("%m")
    date_prefix  = run_ist.strftime("%Y%m%d%H%M")
    slug         = f"{date_prefix}-{_slugify(card.headline)}"
    display_date = run_ist.strftime("%d %b %Y, %I:%M %p IST")

    persona_labels = {
        "retail":         "Retail Investor",
        "fund_manager":   "Fund Manager",
        "hni":            "HNI / Family Office",
        "business_owner": "Business Owner",
        "psu_banker":     "PSU Banker",
    }
    personas_display = [persona_labels.get(p, p) for p in (card.personas_affected or [])]
    sectors_display  = [s.replace("_", " ").title() for s in (card.sectors_affected or [])]

    en_fm = _build_frontmatter_en(card, run_ist, display_date, personas_display, sectors_display)
    hi_fm = _build_frontmatter_hi(card, run_ist, display_date, personas_display, sectors_display)

    en_path = f"content/policy/{year}/{month}/{slug}.md"
    hi_path = f"content/policy/{year}/{month}/{slug}.hi.md"

    return {
        en_path: en_fm,
        hi_path: hi_fm,
    }


def build_policy_section_index(run_dt: datetime) -> dict[str, str]:
    """Ensure Hugo section index files exist for /policy/.
    Safe to call on every run — will not overwrite existing content.
    """
    run_ist = run_dt.astimezone(IST)
    year  = run_ist.strftime("%Y")
    month = run_ist.strftime("%m")
    en_index_path = f"content/policy/{year}/{month}/_index.md"
    en_index = (
        "---\n"
        f'title: "Policy Desk"\n'
        f'date: "{run_ist.isoformat()}"\n'
        "layout: \"policy-list\"\n"
        "---\n"
    )
    return {en_index_path: en_index}
