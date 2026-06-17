"""news_card.py — builds a single all-YAML Hugo Markdown post from a validated ImpactPost.

Architecture decision: 100% YAML frontmatter, empty body.
All bilingual content stored as _en / _hi key pairs.
Hugo template handles rendering logic — Python never writes Markdown headings.

One file per post (slug.md). No separate .hi.md file.
Hugo i18n reads language from the `language` front-matter key and _en/_hi fields.
"""
from datetime import datetime, timezone, timedelta
from src.ai.schema import ImpactPost
from config.mappings import CATEGORY_LABEL, PERSONA_LABEL, HORIZON_LABEL
from config.settings import IMPACT_SCORE_PREMIUM_THRESHOLD, NEWS_CONTENT_PATH

IST = timezone(timedelta(hours=5, minutes=30))


def _slug(post: ImpactPost, run_dt: datetime) -> str:
    base = (post.content_en.headline if post.content_en else "post").lower()
    base = "".join(c if c.isalnum() or c == " " else "" for c in base)
    base = "-".join(base.split()[:8])
    ts = run_dt.strftime("%Y%m%d-%H%M")
    return f"{ts}-{base}"


def build_section_indexes(run_dt: datetime) -> dict[str, str]:
    year = run_dt.strftime("%Y")
    month_label = run_dt.strftime("%B %Y")
    year_month = run_dt.strftime("%Y/%m")
    return {
        f"{NEWS_CONTENT_PATH}/{year}/_index.md": f'---\ntitle: "{year}"\n---\n',
        f"{NEWS_CONTENT_PATH}/{year_month}/_index.md": f'---\ntitle: "{month_label}"\n---\n',
    }


def _yaml_str(v) -> str:
    """Safely quote a string for YAML — escapes inner double quotes."""
    if v is None:
        return '""'
    return '"' + str(v).replace('"', '\\"') + '"'


def _yaml_list(items: list, indent: int = 2) -> str:
    """Render a list as YAML block sequence."""
    if not items:
        return "[]"
    pad = " " * indent
    return "\n" + "\n".join(f"{pad}- {_yaml_str(i)}" for i in items)


def _yaml_obj_list(items: list[dict], indent: int = 2) -> str:
    """Render a list of dicts as YAML block sequence."""
    if not items:
        return "[]"
    lines = []
    pad = " " * indent
    for obj in items:
        first = True
        for k, v in obj.items():
            prefix = f"{pad}- " if first else f"{pad}  "
            lines.append(f"{prefix}{k}: {_yaml_str(v)}")
            first = False
    return "\n" + "\n".join(lines)


def build_news_card(post: ImpactPost, run_dt: datetime | None = None) -> dict[str, str]:
    """
    Returns dict of {relative_path: markdown_content}.
    Single file per post — all bilingual content in YAML frontmatter.
    Body is empty.
    """
    if run_dt is None:
        run_dt = datetime.now(timezone.utc)

    run_dt_ist  = run_dt.astimezone(IST)
    slug        = _slug(post, run_dt_ist)
    date_str    = run_dt_ist.strftime("%Y-%m-%dT%H:%M:%S+05:30")
    year_month  = run_dt_ist.strftime("%Y/%m")
    path        = f"{NEWS_CONTENT_PATH}/{year_month}/{slug}.md"

    # Resolve enum values safely
    category_val  = post.category.value       if post.category       else "macro"
    persona_val   = post.primary_persona.value if post.primary_persona else "new_investor"
    horizon_val   = post.impact_horizon.value  if post.impact_horizon  else "medium_term"
    sentiment_val = post.sentiment.value       if post.sentiment       else "neutral"
    ct_val        = post.content_type.value    if post.content_type    else "news"
    br_val        = post.behavioral_risk.value if post.behavioral_risk else ""

    category_label = CATEGORY_LABEL.get(category_val, category_val)
    persona_label  = PERSONA_LABEL.get(persona_val, persona_val)
    horizon_label  = HORIZON_LABEL.get(horizon_val, horizon_val)
    premium        = post.editorial_impact_score >= IMPACT_SCORE_PREMIUM_THRESHOLD

    # Content blocks
    en = post.content_en
    hi = post.content_hi

    # Personas
    affected_yaml = _yaml_list(
        [PERSONA_LABEL.get(p.value, p.value) for p in post.affected_personas]
    )

    # Concepts
    concepts_yaml = _yaml_list(post.concepts)

    # Source links
    source_links_yaml = _yaml_obj_list(
        [{"url": s.url, "label": s.label} for s in post.source_links]
    )

    # Learn links
    learn_links_yaml = _yaml_obj_list(
        [{"slug": ll.slug, "title": ll.title, "difficulty": ll.difficulty}
         for ll in post.learn_links]
    )

    content = f"""---
# ── CORE ────────────────────────────────────────────────────────────────────
title:           {_yaml_str(en.headline if en else "")}
title_hi:        {_yaml_str(hi.headline if hi else "")}
date:            {date_str}
draft:           false
content_type:    {_yaml_str(ct_val)}
category:        {_yaml_str(category_label)}
sentiment:       {_yaml_str(sentiment_val)}
impact_horizon:  {_yaml_str(horizon_label)}
primary_persona: {_yaml_str(persona_label)}
affected_personas:{affected_yaml}
concepts:{concepts_yaml}
concept_difficulty: {_yaml_str(post.concept_difficulty)}
premium:         {str(premium).lower()}
push_notify:     {str(post.push_notify).lower()}
shareable:       {str(post.shareable).lower()}
whatsapp_caption: {_yaml_str(post.whatsapp_caption)}

# ── RETAIL LENS ─────────────────────────────────────────────────────────────
who_affected_en:    {_yaml_str(en.who_affected if en else "")}
who_affected_hi:    {_yaml_str(hi.who_affected if hi else "")}
what_changes_en:    {_yaml_str(en.what_changes if en else "")}
what_changes_hi:    {_yaml_str(hi.what_changes if hi else "")}
action_command_en:  {_yaml_str(en.action_to_consider if en else "")}
action_command_hi:  {_yaml_str(hi.action_to_consider if hi else "")}

# ── PRO LENS ─────────────────────────────────────────────────────────────────
behavioral_risk:          {_yaml_str(br_val)}
advisor_talking_point_en: {_yaml_str(post.advisor_talking_point_en)}
advisor_talking_point_hi: {_yaml_str(post.advisor_talking_point_hi)}
advisor_opportunity_en:   {_yaml_str(post.advisor_opportunity_en)}
advisor_opportunity_hi:   {_yaml_str(post.advisor_opportunity_hi)}

# ── DEEP DIVE ────────────────────────────────────────────────────────────────
learn_links: {learn_links_yaml}

# ── SOURCE LINKS ─────────────────────────────────────────────────────────────
source_links: {source_links_yaml}

# ── SCORING AUDIT (not rendered to users) ────────────────────────────────────
scoring:
  gate_action:             {_yaml_str(post.gate_action)}
  editorial_impact_score:  {post.editorial_impact_score}
  reach_score:             {post.reach_score}
  reach_reasoning:         {_yaml_str(post.reach_reasoning)}
  immediacy_score:         {post.immediacy_score}
  immediacy_reasoning:     {_yaml_str(post.immediacy_reasoning)}
  materiality_score:       {post.materiality_score}
  materiality_reasoning:   {_yaml_str(post.materiality_reasoning)}
  surprise_score:          {post.surprise_score}
  surprise_reasoning:      {_yaml_str(post.surprise_reasoning)}
  actionability_score:     {post.actionability_score}
  actionability_reasoning: {_yaml_str(post.actionability_reasoning)}
  validation_failed:       {str(post.validation_failed).lower()}
  validation_warnings:     {"[]" if not post.validation_warnings else str(post.validation_warnings)}
---
"""

    return {path: content}
