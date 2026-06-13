"""news_card.py — builds Hugo Markdown posts (EN + HI) from a validated ImpactPost."""
from datetime import datetime, timezone
from src.ai.schema import ImpactPost, ImpactContent
from config.mappings import CATEGORY_LABEL, PERSONA_LABEL, HORIZON_LABEL
from config.settings import IMPACT_SCORE_PREMIUM_THRESHOLD, NEWS_CONTENT_PATH


def _slug(post: ImpactPost, run_dt: datetime) -> str:
    base = post.content_en.headline.lower()
    base = "".join(c if c.isalnum() or c == " " else "" for c in base)
    base = "-".join(base.split()[:8])
    ts = run_dt.strftime("%Y%m%d-%H%M")
    return f"{ts}-{base}"


def build_section_indexes(run_dt: datetime) -> dict[str, str]:
    year = run_dt.strftime("%Y")
    month_label = run_dt.strftime("%B %Y")
    year_month = run_dt.strftime("%Y/%m")
    return {
        f"{NEWS_CONTENT_PATH}/{year}/_index.md": f"---\ntitle: \"{year}\"\n---\n",
        f"{NEWS_CONTENT_PATH}/{year_month}/_index.md": f"---\ntitle: \"{month_label}\"\n---\n",
    }


def _frontmatter(post: ImpactPost, title: str, date_str: str, lang: str) -> str:
    category_label = CATEGORY_LABEL.get(post.category.value, post.category.value)
    persona_label = PERSONA_LABEL.get(post.primary_persona.value, post.primary_persona.value)
    horizon_label = HORIZON_LABEL.get(post.impact_horizon.value, post.impact_horizon.value)
    premium = post.editorial_impact_score >= IMPACT_SCORE_PREMIUM_THRESHOLD

    subject_tags_yaml = "\n".join(f'  - "{t}"' for t in post.subject_tags)
    personas_yaml = "\n".join(f'  - "{PERSONA_LABEL.get(p.value, p.value)}"' for p in post.affected_personas)
    concepts_yaml = "\n".join(f'  - "{c}"' for c in post.concepts)
    source_links_yaml = "\n".join(
        f'  - url: "{s.url}"\n    label: "{s.label}"' for s in post.source_links
    )
    learn_links_yaml = "\n".join(
        f'  - slug: "{l.slug}"\n    title: "{l.title}"\n    difficulty: "{l.difficulty}"'
        for l in post.learn_links
    )

    return f"""---
title: "{title}"
date: {date_str}
draft: false
language: {lang}
category: "{category_label}"
sentiment: "{post.sentiment.value}"
primary_persona: "{persona_label}"
affected_personas:
{personas_yaml}
impact_horizon: "{horizon_label}"
editorial_impact_score: {post.editorial_impact_score}
premium: {str(premium).lower()}
shareable: {str(post.shareable).lower()}
push_notify: {str(post.push_notify).lower()}
trigger_event: "{post.trigger_event}"
subject_tags:
{subject_tags_yaml}
concepts:
{concepts_yaml}
concept_difficulty: "{post.concept_difficulty}"
whatsapp_caption: "{post.whatsapp_caption}"
source_links:
{source_links_yaml}
learn_links:
{learn_links_yaml}
---
"""


def _body_en(c: ImpactContent) -> str:
    return f"""## Who is affected

{c.who_affected}

## What changes

{c.what_changes}

## Why this matters

{c.sentiment_reason}

## What you can do

{c.action_to_consider}
"""


def _body_hi(c: ImpactContent) -> str:
    return f"""## Kise prabhavit karta hai

{c.who_affected}

## Kya badlega

{c.what_changes}

## Kyun zaroori hai

{c.sentiment_reason}

## Aap kya kar sakte hain

{c.action_to_consider}
"""


def build_news_card(post: ImpactPost, run_dt: datetime | None = None) -> dict[str, str]:
    """
    Returns dict of {relative_path: markdown_content}.
    Always returns both EN and HI files.
    """
    if run_dt is None:
        run_dt = datetime.now(timezone.utc)

    slug = _slug(post, run_dt)
    date_str = run_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    year_month = run_dt.strftime("%Y/%m")

    en_path = f"{NEWS_CONTENT_PATH}/{year_month}/{slug}.md"
    hi_path = f"{NEWS_CONTENT_PATH}/{year_month}/{slug}.hi.md"

    en_content = _frontmatter(post, post.content_en.headline, date_str, "en") + _body_en(post.content_en)
    hi_content = _frontmatter(post, post.content_hi.headline, date_str, "hi") + _body_hi(post.content_hi)

    return {en_path: en_content, hi_path: hi_content}
