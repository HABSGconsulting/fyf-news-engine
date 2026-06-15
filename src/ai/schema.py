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
# ---------------------------------------------------------------------------

_HARD_BLOCKS: set[tuple[str, str]] = {
    ("immediate",  "behavioral"),
    ("structural", "performance"),
    ("long_term",  "performance"),
    ("structural", "behavioral"),
}

_SOFT_FLAGS: dict[tuple[str, str], str] = {
    ("immediate",  "macro"):      "Macro events tagged immediate are rare. Verify reasoning.",
    ("immediate",  "taxation"):   "Taxation changes rarely take immediate effect. Verify enactment date.",
    ("immediate",  "sectoral"):   "Sectoral shifts are usually gradual. Verify immediate impact claim.",
    ("structural", "product"):    "Product changes are rarely structural. Verify scope and permanence.",
    ("long_term",  "behavioral"): "Behavioural trends are usually short/medium term. Verify long-term claim.",
}


class ImpactPost(BaseModel):
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

    sentiment:       Optional[Sentiment]     = Field(default=None)
    category:        Optional[Category]      = Field(default=None)
    subject_tags:    Optional[list[str]]     = Field(default=None)
    trigger_event:   str                     = Field(default="")
    event_series:    Optional[EventSeries]   = None

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

    more_reads_title:     Optional[str] = Field(default=None)
    more_reads_url:       Optional[str] = Field(default=None)
    more_reads_one_liner: Optional[str] = Field(default=None)

    validation_failed:   bool                  = Field(default=False)
    validation_warnings: List[Dict[str, Any]]  = Field(default_factory=list)

    @field_validator("reach_score", "immediacy_score", "materiality_score",
                     "surprise_score", "source_score", mode="before")
    @classmethod
    def coerce_none_score(cls, v):
        return v if v is not None else 0

    @field_validator("editorial_impact_score", mode="after")
    @classmethod
    def validate_score_is_sum(cls, v: int, info) -> int:
        d = info.data
        fields = ["reach_score", "immediacy_score", "materiality_score", "surprise_score", "source_score"]
        if all(f in d for f in fields):
            expected = sum(d[f] for f in fields)
            if v != expected:
                print(
                    f"  [SCHEMA] editorial_impact_score mismatch — Gemini said {v}, "
                    f"correcting to {expected} (sum of dimension scores)"
                )
                return expected
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

    @field_validator("subject_tags", mode="before")
    @classmethod
    def coerce_subject_tags(cls, v):
        return v if isinstance(v, list) else None

    @field_validator("push_notify", mode="before")
    @classmethod
    def coerce_push_notify(cls, v):
        return bool(v) if v is not None else False

    @model_validator(mode="after")
    def validate_horizon_constraints(self) -> "ImpactPost":
        if self.gate_action in ("Skip entirely", "More Reads"):
            return self
        if not self.category or not self.impact_horizon:
            return self

        cat     = self.category.value
        horizon = self.impact_horizon.value

        if (horizon, cat) in _HARD_BLOCKS:
            raise ValueError(
                f"Logical mismatch: category '{cat}' cannot have impact_horizon '{horizon}'. "
                "Review both fields and correct the less certain one."
            )

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
    """All evaluated items from a single pipeline run — qualifying and non-qualifying."""
    evaluated_items: list[ImpactPost] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PolicyCard — used exclusively for feed_type: policy items
# ---------------------------------------------------------------------------

POLICY_HORIZON_VALUES = Literal[
    "Immediate",
    "Near-term (0-12M)",
    "Cyclical (1-3Y)",
    "Structural (3-5Y+)",
    "Pending Parliament",
]


class PolicyCard(BaseModel):
    """
    Institutional-grade intelligence card for a single PIB / SEBI / RBI / MCA policy release.
    Uses a Tri-Partite Analyst Block (context_and_trigger, mechanism_of_impact, forward_outlook).
    Hard gate at relevance_score >= 6. Items below 6 are dropped and stripped.
    Gemini does NOT set gate_action — the model_validator sets it deterministically.
    source_url is stamped from RSS item AFTER Gemini responds (never trust LLM URL reproduction).
    """
    ministry: str = Field(
        description="Exact formal name of the issuing government entity or regulator. E.g. 'Reserve Bank of India', 'Ministry of Finance', 'CCEA', 'SEBI', 'IFSC Authority'."
    )
    decision_type: str = Field(
        description="Classification: 'Approval' | 'Circular' | 'Framework' | 'Scheme' | 'Amendment' | 'Directive' | 'Notification'"
    )
    headline: str = Field(
        description=(
            "Factual, decision-focused title. Completely strip out political, vague, or congratulatory PR framing. "
            "Extract the exact actionable decision or structural policy shift. "
            "Do NOT replicate PR titles like 'PM addresses conference...' or 'Minister inaugurates...'. "
            "If no real decision exists, set relevance_score to 1 or 2."
        )
    )

    # --- TRI-PARTITE ANALYST BLOCK ---
    context_and_trigger: Optional[str] = Field(
        default=None,
        description=(
            "1 concise sentence: The macro context, structural deficit, or economic problem "
            "this policy intends to solve. Required when relevance_score >= 6."
        )
    )
    mechanism_of_impact: Optional[str] = Field(
        default=None,
        description=(
            "1 concise sentence: The exact fiscal, compliance, or regulatory lever pulled "
            "by this administrative decision. Required when relevance_score >= 6."
        )
    )
    forward_outlook: Optional[str] = Field(
        default=None,
        description=(
            "1 precise sentence: The 12-36 month forward-looking trajectory for asset allocation "
            "or business operations. NO stock names, tickers, or advisory directives. "
            "Required when relevance_score >= 6."
        )
    )

    personas_affected: List[str] = Field(
        default_factory=list,
        description="Target segments. Subset of: ['retail', 'fund_manager', 'hni', 'business_owner', 'psu_banker']. Min 1."
    )
    sectors_affected: List[str] = Field(
        default_factory=list,
        description=(
            "Impacted sectors. Minimalist tokens from: banking, insurance, infra, consumption, "
            "microfinance, sme_lending, capital_markets, real_estate, energy, agriculture, "
            "defence, taxation, fintech, healthcare, education. Min 1."
        )
    )
    horizon: str = Field(
        description=(
            "Select EXACTLY one of these 5 values:\n"
            "  'Immediate'           — gazette notification / RBI circular effective today or this quarter\n"
            "  'Near-term (0-12M)'   — tied to upcoming Union Budget or current FY targets\n"
            "  'Cyclical (1-3Y)'     — multi-year PLI, credit guarantee schemes, fiscal spending cycles\n"
            "  'Structural (3-5Y+)'  — multi-ministry frameworks, deep legal reform, national masterplans\n"
            "  'Pending Parliament'  — cabinet approval for bill not yet passed into law"
        )
    )
    materiality_flag: bool = Field(
        default=False,
        description="Auto-set to True by validator if relevance_score >= 8. Do not set manually."
    )
    materiality_reason: Optional[str] = Field(
        default=None,
        description="Required when materiality_flag is True. One sentence explaining why this is a macro paradigm shift."
    )
    market_lens: Optional[str] = Field(
        default=None,
        description=(
            "Required when materiality_flag is True. Time-boxed to next 12-18 months. "
            "Use probability language: 'raises probability of...', 'reduces regulatory friction for...'. "
            "NO stock names, tickers, or price targets."
        )
    )
    relevance_score: int = Field(
        ge=1, le=10,
        description=(
            "Ruthless 1-10 structural capital market impact score.\n"
            "1-3: PR fluff, inaugurations, foundation stones, MoUs without fiscal backing — SKIP.\n"
            "4-5: Administrative routine, procedural clarifications, localized micro-grants — SKIP.\n"
            "6-7: Direct regulatory changes by SEBI/RBI, FDI cap revisions, Cabinet strategic approvals — PUBLISH.\n"
            "8-10: Systemic fiscal amendments, sweeping code changes, market-wide capital adjustments — PUBLISH as KEY SHIFT."
        )
    )
    sentiment: str = Field(
        default="neutral",
        description="Market directional bias: 'positive' | 'negative' | 'neutral' | 'watch'"
    )
    source_url: str = Field(
        default="",
        description="Stamped from RSS item after Gemini responds. Leave as empty string."
    )
    gate_action: str = Field(
        default="",
        description="Leave as empty string. Set deterministically by model_validator from relevance_score."
    )

    @field_validator("personas_affected", "sectors_affected", mode="before")
    @classmethod
    def coerce_list_fields(cls, v):
        return v if isinstance(v, list) else []

    @field_validator("source_url", "sentiment", mode="before")
    @classmethod
    def coerce_str_fields(cls, v):
        return v if isinstance(v, str) and v.strip() else ""

    @model_validator(mode="after")
    def enforce_institutional_gating(self) -> "PolicyCard":
        # 1. Sentinel: guarantee sentiment is always a valid value
        _VALID_SENTIMENTS = {"positive", "negative", "neutral", "watch"}
        if not self.sentiment or self.sentiment.strip() not in _VALID_SENTIMENTS:
            self.sentiment = "neutral"

        # 2. HARD GATE: below 6 is permanently dropped
        if self.relevance_score < 6:
            self.gate_action = "Skip entirely"
            self.materiality_flag = False
            self.context_and_trigger = None
            self.mechanism_of_impact = None
            self.forward_outlook = None
            self.materiality_reason = None
            self.market_lens = None
            return self

        # 3. Published items (score >= 6): enforce complete Tri-Partite block
        self.gate_action = "Policy Desk"
        if not self.context_and_trigger or not self.mechanism_of_impact or not self.forward_outlook:
            raise ValueError(
                "Complete Tri-Partite analyst block (context_and_trigger, mechanism_of_impact, "
                "forward_outlook) is required for relevance_score >= 6."
            )

        # 4. Auto-promote materiality for score >= 8
        if self.relevance_score >= 8:
            self.materiality_flag = True

        # 5. Material items must have justification fields
        if self.materiality_flag:
            if not self.materiality_reason or not self.materiality_reason.strip():
                raise ValueError("materiality_reason is required when materiality_flag is True.")
            if not self.market_lens or not self.market_lens.strip():
                raise ValueError("market_lens is required when materiality_flag is True.")
        else:
            self.materiality_reason = None
            self.market_lens = None

        return self


class PolicyRunOutput(BaseModel):
    """All evaluated policy items from a single pipeline run."""
    evaluated_items: list[PolicyCard] = Field(default_factory=list)
