"""
persona_map.py — Single source of truth for the 3-layer persona matrix.

Layers:
  BACKEND   → Persona enum value (stored in D1, written to frontmatter)
  GEMINI    → Description string sent in system_prompt.txt (tells the model who this person is)
  UI LABEL  → Display string shown on the news card badge in the frontend

Usage in Hugo templates (via .Site.Data or JSON endpoint):
  {{ index site.Data.persona_labels .Params.primary_persona }}
  → "Mutual Fund Investors"

Usage in Python (news_card builder, tests):
  from src.ai.persona_map import PERSONA_UI_LABEL
  label = PERSONA_UI_LABEL["mutual_fund_investor"]   # → "Mutual Fund Investors"
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# The canonical 3-layer matrix
# ---------------------------------------------------------------------------
#  (backend_enum, gemini_context, ui_label)
_MATRIX: list[tuple[str, str, str]] = [
    (
        "mutual_fund_investor",
        "Mutual Fund & SIP Investors — people who invest via monthly SIPs, lumpsum investments, SWPs, debt funds, equity funds, or ELSS. Sensitive to NAV changes, TER cuts, new fund rules, taxation of MF gains.",
        "Mutual Fund Investors",
    ),
    (
        "retail_borrower",
        "Home Loan & Retail Borrowers — individuals with floating or fixed rate home loans, car loans, or personal loans. Highly sensitive to RBI repo rate decisions and bank lending rate changes that directly move their monthly EMI.",
        "Retail Borrowers",
    ),
    (
        "fixed_income_investor",
        "Retirees & Fixed Income Investors — people dependent on predictable yield from FDs, Senior Citizen Savings Schemes, bonds, debt mutual funds, annuities, or NPS. Sensitive to interest rate direction and capital safety.",
        "Fixed Income Seekers",
    ),
    (
        "long_term_investor",
        "Direct Equity Long-Term Investors — fundamental investors who hold individual stocks for years based on business quality and valuation. React to earnings, governance, sector tailwinds, and regulatory changes affecting listed companies. Distinct from traders.",
        "Core Equity Investors",
    ),
    (
        "active_trader",
        "Active F&O / Day Traders — short-term momentum and derivatives traders sensitive to index levels, volatility, F&O margin rules, SEBI position limit changes, and intraday regulatory actions. Distinct from long-term investors.",
        "Active Traders",
    ),
    (
        "salaried_taxpayer",
        "Salaried Taxpayers — salaried individuals choosing between old and new tax regimes, optimising 80C, HRA, NPS deductions, and tracking income tax slab changes, TDS rules, and budget tax proposals.",
        "Taxpayers",
    ),
    (
        "new_investor",
        "Millennial / Gen-Z Beginners — first-time investors entering equity or MF markets. Need simple, jargon-free explanations. Sensitive to low-cost product launches, basic KYC/account rule changes, and beginner-relevant scheme announcements.",
        "New Investors",
    ),
    (
        "business_owner",
        "Tech / Gig / MSME Earners & Business Owners — self-employed individuals, freelancers, and small business owners with irregular income. Sensitive to GST changes, advance tax, presumptive taxation, MSME credit policy, and payment gateway regulation.",
        "Business Owners & Gig Earners",
    ),
]

# ---------------------------------------------------------------------------
# Derived lookups — import these directly in Python code
# ---------------------------------------------------------------------------

# backend_enum → UI label (use in Hugo data files and news_card builder)
PERSONA_UI_LABEL: dict[str, str] = {row[0]: row[2] for row in _MATRIX}

# backend_enum → Gemini context string (auto-injected into system_prompt.txt at build time)
PERSONA_GEMINI_CONTEXT: dict[str, str] = {row[0]: row[1] for row in _MATRIX}

# Full ordered list of backend enum values (use for validation and ordering)
PERSONA_ENUM_VALUES: list[str] = [row[0] for row in _MATRIX]


def personas_to_ui_labels(personas: list[str]) -> list[str]:
    """Convert a list of backend enum strings to UI display labels.

    Args:
        personas: e.g. ["mutual_fund_investor", "salaried_taxpayer"]

    Returns:
        e.g. ["Mutual Fund Investors", "Taxpayers"]
    """
    return [PERSONA_UI_LABEL.get(p, p) for p in personas]


def primary_badge(primary_persona: str | None) -> str:
    """Return the 'RELEVANT FOR: <UI LABEL>' badge string for card rendering.

    Args:
        primary_persona: backend enum string or None

    Returns:
        e.g. "RELEVANT FOR: MUTUAL FUND INVESTORS"
        Returns empty string if persona is None.
    """
    if not primary_persona:
        return ""
    label = PERSONA_UI_LABEL.get(primary_persona, primary_persona)
    return f"RELEVANT FOR: {label.upper()}"


def secondary_badges(affected_personas: list[str], primary_persona: str | None) -> list[str]:
    """Return UI labels for secondary persona badges.

    Design rule: secondary badges only appear when reach_score == 2
    (i.e. the story affects 3+ personas). The primary persona is excluded
    from this list to avoid duplication. Max 3 secondary badges displayed.

    Args:
        affected_personas: full list from ImpactPost.affected_personas
        primary_persona:   primary persona enum string (excluded from result)

    Returns:
        List of UI label strings, primary excluded, max 3 items.
    """
    secondary = [
        PERSONA_UI_LABEL.get(p, p)
        for p in affected_personas
        if p != primary_persona
    ]
    return secondary[:3]
