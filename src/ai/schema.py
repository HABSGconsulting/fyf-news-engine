from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from enum import Enum


class Category(str, Enum):
    MACRO = "macro"
    REGULATORY = "regulatory"
    PERFORMANCE = "performance"
    PRODUCT = "product"
    HOUSE = "house"
    TAXATION = "taxation"
    SECTORAL = "sectoral"
    BEHAVIORAL = "behavioral"


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
    NEUTRAL = "neutral"
    WATCH = "watch"


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
    headline:          str = Field(description="Investor-framed headline. Lead with the investor.")
    who_affected:      str = Field(description="One sentence: exact investor type and why affected")
    what_changes:      str = Field(description="One sentence: what materially changes for them")
    sentiment_reason:  str = Field(description="One sentence: why this sentiment tag")
    action_to_consider:str = Field(description="One concrete non-advisory action investor can take")


class LearnLink(BaseModel):
    slug:       str
    title:      str
    difficulty: str  # beginner | intermediate | advanced


class SourceLink(BaseModel):
    url:   str
    label: str


class ImpactPost(BaseModel):
    # ------------------------------------------------------------------
    # Chain-of-Thought scoring (filled for ALL items, including skips)
    # ------------------------------------------------------------------
    reach_score:       int = Field(ge=0, le=2, description="0: institutional only. 1: 1-2 personas. 2: 3+ personas.")
    reach_reasoning:   str = Field(description="1-sentence justification for reach_score.")

    immediacy_score:   int = Field(ge=0, le=2, description="0: long-term background. 1: 1-6 months. 2: days/weeks or immediate.")
    immediacy_reasoning: str = Field(description="1-sentence justification for immediacy_score.")

    materiality_score: int = Field(ge=0, le=2, description="0: opinion/no wallet impact. 1: indirect sector impact. 2: direct EMI/tax/fund cost change.")
    materiality_reasoning: str = Field(description="1-sentence justification for materiality_score.")

    surprise_score:    int = Field(ge=0, le=2, description="0: fully priced in. 1: partial surprise. 2: unexpected/landmark.")
    surprise_reasoning: str = Field(description="1-sentence justification for surprise_score.")

    source_score:      int = Field(ge=0, le=2, description="0: rumour/analyst opinion. 1: credible draft/proposal. 2: official final circular/gazette.")
    source_reasoning:  str = Field(description="1-sentence justification for source_score.")

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
    # Validators
    # ------------------------------------------------------------------
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


class RunOutput(BaseModel):
    """All evaluated items from a single pipeline run — qualifying and non-qualifying.
    main.py routes items by gate_action:
      'Impact post*'  → news_card builder → fyf-news-site
      'More Reads'    → more_reads builder → data/more-reads/
      'Skip entirely' → discarded, counted in run log only
    """
    evaluated_items: list[ImpactPost] = Field(default_factory=list)
