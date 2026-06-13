from pydantic import BaseModel, Field, field_validator
from typing import Optional
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
    SIP_INVESTOR = "sip_investor"
    HOME_LOAN_HOLDER = "home_loan_holder"
    RETIREE = "retiree"
    FIXED_INCOME = "fixed_income_investor"
    TAX_PLANNER = "tax_planner"
    NEW_INVESTOR = "new_investor"
    EQUITY_TRADER = "equity_trader"
    BUSINESS_OWNER = "business_owner"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    WATCH = "watch"


class ImpactHorizon(str, Enum):
    IMMEDIATE = "immediate"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"
    STRUCTURAL = "structural"


class EventSeries(str, Enum):
    RBI_MPC = "RBI_MPC"
    UNION_BUDGET = "UNION_BUDGET"
    SEBI_BOARD = "SEBI_BOARD"
    QUARTERLY_RESULTS = "QUARTERLY_RESULTS"
    ANNUAL_INFLATION = "ANNUAL_INFLATION"
    NIFTY_MILESTONE = "NIFTY_MILESTONE"
    FII_FLOW_TREND = "FII_FLOW_TREND"


class ImpactContent(BaseModel):
    headline: str = Field(description="Investor-framed headline. Lead with the investor.")
    who_affected: str = Field(description="One sentence: exact investor type and why affected")
    what_changes: str = Field(description="One sentence: what materially changes for them")
    sentiment_reason: str = Field(description="One sentence: why this sentiment tag")
    action_to_consider: str = Field(description="One concrete non-advisory action investor can take")


class LearnLink(BaseModel):
    slug: str
    title: str
    difficulty: str  # beginner | intermediate | advanced


class SourceLink(BaseModel):
    url: str
    label: str


class ImpactPost(BaseModel):
    editorial_impact_score: int = Field(ge=1, le=10)
    sentiment: Sentiment
    category: Category
    subject_tags: list[str] = Field(default_factory=list)
    trigger_event: str = Field(default="")
    event_series: Optional[EventSeries] = None
    primary_persona: Persona
    affected_personas: list[Persona] = Field(default_factory=list)
    impact_horizon: ImpactHorizon
    concepts: list[str] = Field(default_factory=list)
    concept_difficulty: str = Field(default="beginner")
    content_en: ImpactContent
    content_hi: ImpactContent
    learn_links: list[LearnLink] = Field(default_factory=list)
    source_links: list[SourceLink] = Field(max_length=3, default_factory=list)
    shareable: bool = True
    push_notify: bool = False
    whatsapp_caption: str = Field(default="")

    @field_validator("trigger_event", mode="before")
    @classmethod
    def coerce_trigger_event(cls, v):
        return v or ""

    @field_validator("whatsapp_caption", mode="before")
    @classmethod
    def coerce_whatsapp_caption(cls, v):
        return v or ""

    @field_validator("concept_difficulty", mode="before")
    @classmethod
    def coerce_concept_difficulty(cls, v):
        return v if v in ("beginner", "intermediate", "advanced") else "beginner"


class MoreReadsItem(BaseModel):
    title: str
    url: str
    one_liner: str
    category: Category


class RunOutput(BaseModel):
    impact_posts: list[ImpactPost] = Field(min_length=0, max_length=5)
    more_reads: list[MoreReadsItem] = Field(default_factory=list)
