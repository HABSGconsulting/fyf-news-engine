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


class BehavioralRisk(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class ContentType(str, Enum):
    NEWS             = "news"
    VIEW             = "view"
    SOFT_NEWS        = "soft_news"
    REGULATORY_DRAFT = "regulatory_draft"


class EventSeries(str, Enum):
    RBI_MPC           = "RBI_MPC"
    UNION_BUDGET      = "UNION_BUDGET"
    SEBI_BOARD        = "SEBI_BOARD"
    QUARTERLY_RESULTS = "QUARTERLY_RESULTS"
    ANNUAL_INFLATION  = "ANNUAL_INFLATION"
    NIFTY_MILESTONE   = "NIFTY_MILESTONE"
    FII_FLOW_TREND    = "FII_FLOW_TREND"


# ---------------------------------------------------------------------------
# Pass 1 — Scoring only (lightweight, zero content)
# ---------------------------------------------------------------------------

class ScoreItem(BaseModel):
    """Lightweight scoring result for a single news item from Pass 1."""
    index:                   int
    content_type:            ContentType
    reach_score:             int = Field(ge=0, le=2)
    reach_reasoning:         str
    immediacy_score:         int = Field(ge=0, le=2)
    immediacy_reasoning:     str
    materiality_score:       int = Field(ge=0, le=2)
    materiality_reasoning:   str
    surprise_score:          int = Field(ge=0, le=2)
    surprise_reasoning:      str
    actionability_score:     int = Field(ge=0, le=2)
    actionability_reasoning: str
    editorial_impact_score:  int = Field(ge=0, le=10)
    gate_action:             str

    @field_validator("reach_score", "immediacy_score", "materiality_score",
                     "surprise_score", "actionability_score", mode="before")
    @classmethod
    def coerce_none_score(cls, v):
        return v if v is not None else 0

    @model_validator(mode="after")
    def fix_score_sum(self) -> "ScoreItem":
        expected = (self.reach_score + self.immediacy_score +
                    self.materiality_score + self.surprise_score +
                    self.actionability_score)
        if self.editorial_impact_score != expected:
            self.editorial_impact_score = expected
        if self.content_type == ContentType.VIEW:
            self.gate_action = "Skip entirely"
            self.editorial_impact_score = 0
        if self.content_type == ContentType.SOFT_NEWS:
            if self.gate_action not in ("Skip entirely", "More Reads"):
                self.gate_action = "More Reads"
        return self


class ScoreOutput(BaseModel):
    """Full Pass 1 response — one ScoreItem per input news item."""
    scores: List[ScoreItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pass 2 — Full content (only for qualifying items)
# ---------------------------------------------------------------------------

class ImpactContent(BaseModel):
    headline:           str
    who_affected:       str
    what_changes:       str
    action_to_consider: str


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
# Horizon x Category constraint tables
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
    # --- Scores carried over from Pass 1 ---
    reach_score:             int = Field(ge=0, le=2)
    reach_reasoning:         str = Field(default="")
    immediacy_score:         int = Field(ge=0, le=2)
    immediacy_reasoning:     str = Field(default="")
    materiality_score:       int = Field(ge=0, le=2)
    materiality_reasoning:   str = Field(default="")
    surprise_score:          int = Field(ge=0, le=2)
    surprise_reasoning:      str = Field(default="")
    actionability_score:     int = Field(ge=0, le=2, default=0)
    actionability_reasoning: str = Field(default="")
    editorial_impact_score:  int = Field(ge=0, le=10)
    gate_action:             Literal[
        "Skip entirely",
        "More Reads",
        "Impact post",
        "Impact post + Premium",
        "Impact post + Premium + Blog",
    ]
    content_type: ContentType = Field(default=ContentType.NEWS)

    # --- Pass 2 content fields ---
    sentiment:          Optional[Sentiment]     = Field(default=None)
    category:           Optional[Category]      = Field(default=None)
    subject_tags:       Optional[list[str]]     = Field(default=None)
    trigger_event:      str                     = Field(default="")
    event_series:       Optional[EventSeries]   = None
    primary_persona:    Optional[Persona]       = Field(default=None)
    affected_personas:  list[Persona]           = Field(default_factory=list)
    impact_horizon:     Optional[ImpactHorizon] = Field(default=None)
    concepts:           list[str]               = Field(default_factory=list)
    concept_difficulty: str                     = Field(default="beginner")
    content_en:         Optional[ImpactContent] = Field(default=None)
    content_hi:         Optional[ImpactContent] = Field(default=None)
    learn_links:        list[LearnLink]         = Field(default_factory=list)
    source_links:       list[SourceLink]        = Field(default_factory=list, max_length=3)
    shareable:          bool                    = True
    push_notify:        bool                    = False
    whatsapp_caption:   str                     = Field(default="")

    # --- Pro fields — bilingual, advisor-facing ---
    behavioral_risk:           Optional[BehavioralRisk] = Field(default=None)
    advisor_talking_point_en:  Optional[str]            = Field(default=None)
    advisor_talking_point_hi:  Optional[str]            = Field(default=None)
    advisor_opportunity_en:    Optional[str]            = Field(default=None)
    advisor_opportunity_hi:    Optional[str]            = Field(default=None)

    # --- More Reads fields ---
    more_reads_title:     Optional[str] = Field(default=None)
    more_reads_url:       Optional[str] = Field(default=None)
    more_reads_one_liner: Optional[str] = Field(default=None)

    # --- Internal validation flags ---
    validation_failed:   bool                 = Field(default=False)
    validation_warnings: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("reach_score", "immediacy_score", "materiality_score",
                     "surprise_score", "actionability_score", mode="before")
    @classmethod
    def coerce_none_score(cls, v):
        return v if v is not None else 0

    @field_validator("concepts", "learn_links", "source_links", mode="before")
    @classmethod
    def coerce_none_lists(cls, v):
        return v if isinstance(v, list) else []

    @field_validator("affected_personas", mode="before")
    @classmethod
    def coerce_affected_personas(cls, v):
        return v if isinstance(v, list) else []

    @field_validator("shareable", mode="before")
    @classmethod
    def coerce_shareable(cls, v):
        return bool(v) if v is not None else True

    @field_validator("push_notify", mode="before")
    @classmethod
    def coerce_push_notify(cls, v):
        return bool(v) if v is not None else False

    @field_validator("trigger_event", "whatsapp_caption", mode="before")
    @classmethod
    def coerce_str_fields(cls, v):
        return v or ""

    @field_validator("concept_difficulty", mode="before")
    @classmethod
    def coerce_concept_difficulty(cls, v):
        return v if v in ("beginner", "intermediate", "advanced") else "beginner"

    @field_validator("subject_tags", mode="before")
    @classmethod
    def coerce_subject_tags(cls, v):
        return v if isinstance(v, list) else None

    @field_validator("editorial_impact_score", mode="after")
    @classmethod
    def validate_score_is_sum(cls, v: int, info) -> int:
        d = info.data
        fields = ["reach_score", "immediacy_score", "materiality_score",
                  "surprise_score", "actionability_score"]
        if all(f in d for f in fields):
            expected = sum(d[f] for f in fields)
            if v != expected:
                print(f"  [SCHEMA] editorial_impact_score mismatch — Gemini said {v}, correcting to {expected}")
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

    @model_validator(mode="after")
    def clear_pro_fields_if_not_actionable(self) -> "ImpactPost":
        """Pro fields only meaningful when actionability_score >= 1."""
        if self.actionability_score == 0:
            self.behavioral_risk          = None
            self.advisor_talking_point_en = None
            self.advisor_talking_point_hi = None
            self.advisor_opportunity_en   = None
            self.advisor_opportunity_hi   = None
        return self


class RunOutput(BaseModel):
    """All evaluated items from a single pipeline run."""
    evaluated_items: list[ImpactPost] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PolicyCard — unchanged, policy path untouched
# ---------------------------------------------------------------------------

POLICY_HORIZON_VALUES = Literal[
    "Immediate",
    "Near-term (0-12M)",
    "Cyclical (1-3Y)",
    "Structural (3-5Y+)",
    "Pending Parliament",
]


class PolicyCard(BaseModel):
    ministry: str
    decision_type: str
    headline: str
    headline_hi: Optional[str] = Field(default=None)
    context_and_trigger: Optional[str] = Field(default=None)
    mechanism_of_impact: Optional[str] = Field(default=None)
    forward_outlook: Optional[str] = Field(default=None)
    context_and_trigger_hi: Optional[str] = Field(default=None)
    mechanism_of_impact_hi: Optional[str] = Field(default=None)
    forward_outlook_hi: Optional[str] = Field(default=None)
    personas_affected: List[str] = Field(default_factory=list)
    sectors_affected: List[str] = Field(default_factory=list)
    horizon: str
    materiality_flag: bool = Field(default=False)
    materiality_reason: Optional[str] = Field(default=None)
    materiality_reason_hi: Optional[str] = Field(default=None)
    market_lens: Optional[str] = Field(default=None)
    market_lens_hi: Optional[str] = Field(default=None)
    relevance_score: int = Field(ge=1, le=10)
    sentiment: str = Field(default="neutral")
    source_url: str = Field(default="")
    gate_action: str = Field(default="")

    @field_validator("personas_affected", "sectors_affected", mode="before")
    @classmethod
    def coerce_list_fields(cls, v):
        return v if isinstance(v, list) else []

    @field_validator("source_url", "sentiment", mode="before")
    @classmethod
    def coerce_str_fields(cls, v):
        return v if isinstance(v, str) and v.strip() else ""

    @field_validator("horizon", mode="before")
    @classmethod
    def coerce_horizon(cls, v):
        valid = {"Immediate", "Near-term (0-12M)", "Cyclical (1-3Y)", "Structural (3-5Y+)", "Pending Parliament"}
        if isinstance(v, str) and v.strip() in valid:
            return v.strip()
        return "Near-term (0-12M)"

    @model_validator(mode="after")
    def enforce_institutional_gating(self) -> "PolicyCard":
        _VALID_SENTIMENTS = {"positive", "negative", "neutral", "watch"}
        if not self.sentiment or self.sentiment.strip() not in _VALID_SENTIMENTS:
            self.sentiment = "neutral"
        if self.relevance_score < 6:
            self.gate_action = "Skip entirely"
            self.materiality_flag = False
            self.context_and_trigger = None
            self.mechanism_of_impact = None
            self.forward_outlook = None
            self.context_and_trigger_hi = None
            self.mechanism_of_impact_hi = None
            self.forward_outlook_hi = None
            self.materiality_reason = None
            self.materiality_reason_hi = None
            self.market_lens = None
            self.market_lens_hi = None
            self.headline_hi = None
            return self
        self.gate_action = "Policy Desk"
        missing_en = not self.context_and_trigger or not self.mechanism_of_impact or not self.forward_outlook
        missing_hi = not self.context_and_trigger_hi or not self.mechanism_of_impact_hi or not self.forward_outlook_hi
        if missing_en:
            raise ValueError("Complete English Tri-Partite analyst block required for relevance_score >= 6.")
        if missing_hi:
            raise ValueError("Complete Hindi Tri-Partite block required for relevance_score >= 6.")
        if not self.headline_hi or not self.headline_hi.strip():
            raise ValueError("headline_hi required for relevance_score >= 6.")
        if self.relevance_score >= 8:
            self.materiality_flag = True
        if self.materiality_flag:
            if not self.materiality_reason or not self.materiality_reason.strip():
                raise ValueError("materiality_reason required when materiality_flag is True.")
            if not self.market_lens or not self.market_lens.strip():
                raise ValueError("market_lens required when materiality_flag is True.")
            if not self.materiality_reason_hi or not self.materiality_reason_hi.strip():
                raise ValueError("materiality_reason_hi required when materiality_flag is True.")
            if not self.market_lens_hi or not self.market_lens_hi.strip():
                raise ValueError("market_lens_hi required when materiality_flag is True.")
        else:
            self.materiality_reason = None
            self.materiality_reason_hi = None
            self.market_lens = None
            self.market_lens_hi = None
        return self


class PolicyRunOutput(BaseModel):
    """All evaluated policy items from a single pipeline run."""
    evaluated_items: list[PolicyCard] = Field(default_factory=list)
