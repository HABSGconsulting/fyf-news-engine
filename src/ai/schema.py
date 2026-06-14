from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal, List, Dict, Any
from enum import Enum


class Category(str, Enum):
    MACRO       = "macro"
    REGULATORY  = "regulatory"
    PERFORMANCE = "performance"
    PRODUCT     = "product"
    HOUSE       = "house"
    TAXATION    = "taxation"
    SECTORAL    = "sectoral"
    BEHAVIORAL  = "behavioral"


class Persona(str, Enum):
    """
    Backend enum values.  One source of truth.
    UI labels and Gemini prompt descriptions live in persona_map.py.

    mutual_fund_investor   → "Mutual Fund & SIP Investors"    → "Mutual Fund Investors"
    retail_borrower        → "Home Loan & Retail Borrowers"   → "Retail Borrowers"
    fixed_income_investor  → "Retirees & Fixed Income"        → "Fixed Income Seekers"
    long_term_investor     → "Direct Equity Long-Term"        → "Core Equity Investors"
    active_trader          → "Active F&O / Day Traders"       → "Active Traders"
    salaried_taxpayer      → "Salaried Taxpayers"             → "Taxpayers"
    new_investor           → "Millennial/Gen-Z Beginners"     → "New Investors"
    business_owner         → "Tech / Gig / MSME Earners"     → "Business Owners & Gig Earners"
    """
    MUTUAL_FUND_INVESTOR  = "mutual_fund_investor"
    RETAIL_BORROWER       = "retail_borrower"
    FIXED_INCOME_INVESTOR = "fixed_income_investor"
    LONG_TERM_INVESTOR    = "long_term_investor"
    ACTIVE_TRADER         = "active_trader"
    SALARIED_TAXPAYER     = "salaried_taxpayer"
    NEW_INVESTOR          = "new_investor"
    BUSINESS_OWNER        = "business_owner"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL  = "neutral"
    WATCH    = "watch"


class ImpactHorizon(str, Enum):
    IMMEDIATE   = "immediate"
    SHORT_TERM  = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM   = "long_term"
    STRUCTURAL  = "structural"


class EventSeries(str, Enum):
    RBI_MPC           = "RBI_MPC"
    UNION_BUDGET      = "UNION_BUDGET"
    SEBI_BOARD        = "SEBI_BOARD"
    QUARTERLY_RESULTS = "QUARTERLY_RESULTS"
    ANNUAL_INFLATION  = "ANNUAL_INFLATION"
    NIFTY_MILESTONE   = "NIFTY_MILESTONE"
    FII_FLOW_TREND    = "FII_FLOW_TREND"


class ImpactContent(BaseModel):
    headline:           str = Field(description="Investor-framed headline. Lead with the investor, not the institution. Max 12 words.")
    who_affected:       str = Field(description="Exactly 1 sentence. Name the persona explicitly. Max 20 words.")
    what_changes:       str = Field(description="Exactly 1 sentence. State what materially changes. MUST include a specific number, metric, or percentage. Max 30 words.")
    # sentiment_reason removed: dead field, wasted tokens. Sentiment is self-evident from sentiment enum + what_changes.
    action_to_consider: str = Field(
        description=(
            "Exactly 1 sentence. One concrete, non-advisory action the investor can take. "
            "Write as if advising a client on a call — direct and conditional on the persona. "
            "If the persona is sip_investor and horizon is short_term, affirm long-term discipline; do not suggest tactical moves. "
            "If no action is warranted, state that explicitly and explain why in the same sentence. "
            "Max 30 words. Active voice. No jargon without explanation."
        )
    )


class LearnLink(BaseModel):
    slug:       str
    title:      str
    difficulty: str  # beginner | intermediate | advanced


class SourceLink(BaseModel):
    url:   str
    label: str


class MoreReadsItem(BaseModel):
    """Lightweight model for score-4 items published to the More Reads section."""
    title:     str
    url:       str
    one_liner: str
    category:  Category


# ---------------------------------------------------------------------------
# Horizon × Category constraint tables
#
# TIER 1 — Hard blocks: logically impossible combinations.
# A ValidationError here causes gemini_client.py to retry the item.
#
# TIER 2 — Soft flags: unusual but plausible combinations.
# Appended to validation_warnings for human review; no retry triggered.
# ---------------------------------------------------------------------------

_HARD_BLOCKS: set[tuple[str, str]] = {
    # (impact_horizon, category)
    ("immediate",  "behavioral"),   # Behavioural change cannot be immediate
    ("structural", "performance"),  # Performance is point-in-time, not structural
    ("long_term",  "performance"),  # Same: performance data is not long-term horizon
    ("structural", "behavioral"),   # Behavioural shifts are medium/long, not structural policy
}

_SOFT_FLAGS: dict[tuple[str, str], str] = {
    ("immediate",  "macro"):      "Macro events tagged immediate are rare. Verify reasoning.",
    ("immediate",  "taxation"):   "Taxation changes rarely take immediate effect. Verify enactment date.",
    ("immediate",  "sectoral"):   "Sectoral shifts are usually gradual. Verify immediate impact claim.",
    ("structural", "product"):    "Product changes are rarely structural. Verify scope and permanence.",
    ("long_term",  "behavioral"): "Behavioural trends are usually short/medium term. Verify long-term claim.",
}


class ImpactPost(BaseModel):
    # ------------------------------------------------------------------
    # Chain-of-Thought scoring (filled for ALL items, including skips)
    # ------------------------------------------------------------------
    reach_score:       int = Field(ge=0, le=2, description="0: institutional only. 1: 1-2 personas. 2: 3+ personas.")
    reach_reasoning:   str = Field(description="1-sentence justification for reach_score.")

    immediacy_score:     int = Field(ge=0, le=2, description="0: long-term background. 1: 1-6 months. 2: days/weeks or already in effect.")
    immediacy_reasoning: str = Field(description="1-sentence justification for immediacy_score.")

    materiality_score:     int = Field(ge=0, le=2, description="0: opinion/no wallet impact. 1: indirect sector impact. 2: direct EMI/tax/fund cost change.")
    materiality_reasoning: str = Field(description="1-sentence justification for materiality_score.")

    surprise_score:     int = Field(ge=0, le=2, description="0: fully priced in. 1: partial surprise. 2: unexpected/landmark.")
    surprise_reasoning: str = Field(description="1-sentence justification for surprise_score.")

    source_score:     int = Field(ge=0, le=2, description="0: rumour/analyst opinion. 1: credible draft/proposal. 2: official final circular/gazette.")
    source_reasoning: str = Field(description="1-sentence justification for source_score.")

    editorial_impact_score: int = Field(
        ge=0, le=10,
        description="MUST equal reach_score + immediacy_score + materiality_score + surprise_score + source_score exactly."
    )

    gate_action: Literal[
        "Skip entirely",
        "More Reads",
        "Impact post",
        "Impact post + Premium",
        "Impact post + Premium + Blog",
    ] = Field(description="Action derived strictly from editorial_impact_score threshold.")

    # ------------------------------------------------------------------
    # Publication fields — None for Skip/More Reads items (saves tokens)
    # ------------------------------------------------------------------
    sentiment:       Optional[Sentiment]     = Field(default=None)
    category:        Optional[Category]      = Field(default=None)
    subject_tags:    list[str]               = Field(default_factory=list)
    trigger_event:   str                     = Field(default="")
    event_series:    Optional[EventSeries]   = None

    # Persona fields
    # primary_persona   → drives the "RELEVANT FOR: <UI LABEL>" badge on the card
    # affected_personas → drives secondary badges (shown only for reach_score == 2)
    # See persona_map.PERSONA_UI_LABEL to resolve enum → display string in templates
    primary_persona:   Optional[Persona]     = Field(default=None)
    affected_personas: list[Persona]         = Field(default_factory=list)

    impact_horizon:    Optional[ImpactHorizon] = Field(default=None)
    concepts:          list[str]             = Field(default_factory=list)
    concept_difficulty: str                  = Field(default="beginner")
    content_en:        Optional[ImpactContent] = Field(default=None)
    content_hi:        Optional[ImpactContent] = Field(default=None)
    learn_links:       list[LearnLink]       = Field(default_factory=list)
    source_links:      list[SourceLink]      = Field(default_factory=list, max_length=3)
    shareable:         bool                  = True
    push_notify:       bool                  = False
    whatsapp_caption:  str                   = Field(default="")

    # More Reads fields — populated when gate_action == "More Reads"
    more_reads_title:     Optional[str] = Field(default=None)
    more_reads_url:       Optional[str] = Field(default=None)
    more_reads_one_liner: Optional[str] = Field(default=None)

    # ------------------------------------------------------------------
    # Validation telemetry — written by model_validators below
    # ------------------------------------------------------------------
    validation_failed:   bool                  = Field(default=False)
    validation_warnings: List[Dict[str, Any]]  = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("editorial_impact_score", mode="after")
    @classmethod
    def validate_score_is_sum(cls, v: int, info) -> int:
        """Catch Gemini arithmetic errors before they affect gate_action."""
        d = info.data
        fields = ["reach_score", "immediacy_score", "materiality_score", "surprise_score", "source_score"]
        if all(f in d for f in fields):
            expected = sum(d[f] for f in fields)
            if v != expected:
                raise ValueError(
                    f"editorial_impact_score {v} does not equal sum of dimension scores "
                    f"({' + '.join(str(d[f]) for f in fields)} = {expected}). "
                    "Recalculate and correct."
                )
        return v

    @field_validator("gate_action")
    @classmethod
    def validate_gate_action(cls, v: str, info) -> str:
        score = info.data.get("editorial_impact_score")
        if score is None:
            return v
        if 0 <= score <= 3 and v != "Skip entirely":
            raise ValueError(f"Score {score} must map to 'Skip entirely', got '{v}'")
        elif score == 4 and v != "More Reads":
            raise ValueError(f"Score {score} must map to 'More Reads', got '{v}'")
        elif 5 <= score <= 6 and v != "Impact post":
            raise ValueError(f"Score {score} must map to 'Impact post', got '{v}'")
        elif 7 <= score <= 8 and v != "Impact post + Premium":
            raise ValueError(f"Score {score} must map to 'Impact post + Premium', got '{v}'")
        elif 9 <= score <= 10 and v != "Impact post + Premium + Blog":
            raise ValueError(f"Score {score} must map to 'Impact post + Premium + Blog', got '{v}'")
        return v

    @field_validator("trigger_event", mode="before")
    @classmethod
    def coerce_trigger_event(cls, v): return v or ""

    @field_validator("whatsapp_caption", mode="before")
    @classmethod
    def coerce_whatsapp_caption(cls, v): return v or ""

    @field_validator("concept_difficulty", mode="before")
    @classmethod
    def coerce_concept_difficulty(cls, v):
        return v if v in ("beginner", "intermediate", "advanced") else "beginner"

    @model_validator(mode="after")
    def validate_horizon_constraints(self) -> "ImpactPost":
        """Two-tier horizon × category validation.

        Tier 1 — Hard blocks: raise ValueError → gemini_client retries the item.
        Tier 2 — Soft flags: append to validation_warnings → logged for review, no retry.
        """
        # Only validate posts that have actual content
        if self.gate_action in ("Skip entirely", "More Reads"):
            return self
        if not self.category or not self.impact_horizon:
            return self

        cat     = self.category.value      # e.g. "behavioral"
        horizon = self.impact_horizon.value  # e.g. "immediate"

        # Tier 1: Hard block
        if (horizon, cat) in _HARD_BLOCKS:
            raise ValueError(
                f"Logical mismatch: category '{cat}' cannot have impact_horizon '{horizon}'. "
                "Review both fields and correct the less certain one."
            )

        # Tier 2: Soft flag
        flag_note = _SOFT_FLAGS.get((horizon, cat))
        if flag_note:
            self.validation_warnings.append({
                "field": "impact_horizon",
                "category": cat,
                "horizon": horizon,
                "flag": f"{cat}_{horizon}_review",
                "note": flag_note,
            })

        return self


class RunOutput(BaseModel):
    """All evaluated items from a single pipeline run — qualifying and non-qualifying.
    main.py routes items by gate_action:
      'Impact post*'  → news_card builder → fyf-news-site
      'More Reads'    → more_reads builder → data/more-reads/
      'Skip entirely' → discarded, counted in run log only
    """
    evaluated_items: list[ImpactPost] = Field(default_factory=list)
