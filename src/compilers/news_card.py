"""news_card.py — builds Hugo Markdown post from a validated ImpactPost."""
from datetime import datetime, timezone
from pathlib import Path
from src.ai.schema import ImpactPost
from config.mappings import CATEGORY_LABEL, PERSONA_LABEL, HORIZON_LABEL
from config.settings import IMPACT_SCORE_PREMIUM_THRESHOLD, NEWS_CONTENT_PATH


def _slug(post: ImpactPost, run_dt: datetime) -> str:
    """Generate a URL-safe slug from headline + timestamp."""
    base = post.content_en.headline.lower()
    base = "".join(c if c.isalnum() or c == " " else "" for c in base)
    base = "-".join(base.split()[:8])
    ts = run_dt.strftime("%Y%m%d-%H%M")
    return f"{ts}-{base}"


def build_news_card(post: ImpactPost, run_dt: datetime | None = None) -> tuple[str, str]:
    """
    Returns (relative_path, markdown_content) for the post.
    relative_path is relative to fyf-news-site repo root.
    """
    if run_dt is None:
        run_dt = datetime.now(timezone.utc)

    slug = _slug(post, run_dt)
    date_str = run_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    year_month = run_dt.strftime("%Y/%m")
    rel_path = f"{NEWS_CONTENT_PATH}/{year_month}/{slug}.md"

    premium = post.editorial_impact_score >= IMPACT_SCORE_PREMIUM_THRESHOLD
    category_label = CATEGORY_LABEL.get(post.category.value, post.category.value)
    persona_label = PERSONA_LABEL.get(post.primary_persona.value, post.primary_persona.value)
    horizon_label = HORIZON_LABEL.get(post.impact_horizon.value, post.impact_horizon.value)

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

    frontmatter = f"""---
title: "{post.content_en.headline}"
date: {date_str}
draft: false
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

    en = post.content_en
    body = f"""## What happened

{en.who_affected}

{en.what_changes}

## Why this matters

{en.sentiment_reason}

## What you can do

{en.action_to_consider}
"""

    return rel_path, frontmatter + body
