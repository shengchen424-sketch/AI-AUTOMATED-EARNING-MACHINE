"""Topic planning, article writing and digital-product creation with Claude."""

from __future__ import annotations

import json
from typing import Any

from .config import Config
from .llm import JSONModel
from .store import slugify

EDITORIAL_RULES = """\
Editorial standards (non-negotiable):
- Be genuinely useful: concrete steps, real workflows, honest trade-offs. No filler.
- Never invent statistics, prices, quotes, studies or features. If unsure, say what to check.
- Recommend a product only when it truly fits the reader's problem; say who it is NOT for.
- No income guarantees, no medical/legal/financial advice beyond general information.
- Write in plain, friendly, expert language for busy small-business owners.

Write so search engines AND AI assistants (ChatGPT, Claude, Perplexity, Google AI Overviews)
can quote you accurately:
- Open every section with one sentence that directly answers its heading, then expand.
- Prefer concrete nouns, numbered steps, named settings/menus, and clear definitions.
- Each paragraph should make sense on its own if quoted out of context.
- Product features and prices change: describe them generally and tell readers to confirm on the vendor's site.
"""

_SECTIONS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "heading": {"type": "string"},
            "paragraphs": {"type": "array", "items": {"type": "string"}},
            "bullets": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["heading", "paragraphs", "bullets"],
        "additionalProperties": False,
    },
}


def _lang_line(cfg: Config) -> str:
    return "Write everything in Simplified Chinese." if cfg.language == "zh" else "Write everything in English."


# ---------------------------------------------------------------------------
# 1. Topic planning
# ---------------------------------------------------------------------------
TOPICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "niche": {"type": "string"},
                    "keyword": {"type": "string"},
                    "title": {"type": "string"},
                    "angle": {"type": "string"},
                    "search_intent": {"type": "string", "enum": ["informational", "commercial", "transactional"]},
                },
                "required": ["niche", "keyword", "title", "angle", "search_intent"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["topics"],
    "additionalProperties": False,
}


def plan_topics(cfg: Config, llm: JSONModel, existing: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    covered = "\n".join(f"- {a['title']} [{a.get('keyword', '')}]" for a in existing[:300]) or "(none yet)"
    prompt = f"""You are the editor-in-chief and SEO strategist of "{cfg.site_name}" — {cfg.tagline}

Niches we cover:
{chr(10).join('- ' + n for n in cfg.niches)}

Already published (do NOT repeat or closely overlap):
{covered}

Propose {count + 3} new article topics. Favour long-tail keywords a new site can rank for,
with clear buyer or problem intent where at least one of our partner tools is a natural fit:
{', '.join(a.name for a in cfg.affiliates)}.
Spread topics across different niches. {_lang_line(cfg)}"""
    data = llm.generate_json(EDITORIAL_RULES, prompt, TOPICS_SCHEMA)
    seen = {slugify(a["title"]) for a in existing} | {slugify(a.get("keyword", "")) for a in existing}
    picked: list[dict[str, Any]] = []
    for t in data["topics"]:
        key, kw = slugify(t["title"]), slugify(t["keyword"])
        if key in seen or kw in seen:
            continue
        seen |= {key, kw}
        picked.append(t)
        if len(picked) == count:
            break
    return picked


# ---------------------------------------------------------------------------
# 2. Article writing
# ---------------------------------------------------------------------------
ARTICLE_VERSION = 2


def article_schema(cfg: Config) -> dict[str, Any]:
    names = [a.name for a in cfg.affiliates] or ["none"]
    strings = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "meta_description": {"type": "string"},
            "quick_answer": {"type": "string"},
            "key_takeaways": strings,
            "who_this_is_for": {"type": "string"},
            "intro": {"type": "string"},
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["name", "text"],
                    "additionalProperties": False,
                },
            },
            "comparison": {
                "type": "object",
                "properties": {
                    "caption": {"type": "string"},
                    "headers": strings,
                    "rows": {"type": "array", "items": strings},
                },
                "required": ["caption", "headers", "rows"],
                "additionalProperties": False,
            },
            "sections": _SECTIONS,
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product": {"type": "string", "enum": names},
                        "best_for": {"type": "string"},
                        "not_for": {"type": "string"},
                    },
                    "required": ["product", "best_for", "not_for"],
                    "additionalProperties": False,
                },
            },
            "faq": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
                    "required": ["question", "answer"],
                    "additionalProperties": False,
                },
            },
            "conclusion": {"type": "string"},
        },
        "required": ["title", "meta_description", "quick_answer", "key_takeaways", "who_this_is_for",
                     "intro", "steps", "comparison", "sections", "recommendations", "faq", "conclusion"],
        "additionalProperties": False,
    }


_ARTICLE_FIELDS_GUIDE = """Field guide:
- title: specific and benefit-led, contains the keyword, under 65 characters if possible.
- meta_description: max 155 characters, compelling, contains the keyword.
- quick_answer: 40–70 words that directly answer the searcher's question. This is the passage
  AI assistants and featured snippets will quote, so make it complete and self-contained.
- key_takeaways: 3–6 crisp bullets a skimmer can act on.
- who_this_is_for: one sentence naming the reader and their situation.
- steps: the core how-to as 4–10 numbered steps (empty array only if the topic is not procedural).
- comparison: a useful table (e.g. options vs criteria) with 2–5 columns and 3–8 rows; use an empty
  caption, headers and rows if a table would not genuinely help.
- sections: 5–8 sections, 1,500–2,200 words in total, keyword used naturally in one heading.
- faq: 3–6 questions people actually search for, each answered in 2–4 sentences.
"""


def _finish(cfg: Config, art: dict[str, Any], topic: dict[str, Any]) -> dict[str, Any]:
    art["recommendations"] = [r for r in art["recommendations"] if cfg.affiliate(r["product"])]
    art.update(keyword=topic["keyword"], niche=topic["niche"], version=ARTICLE_VERSION)
    return art


def edit_article(cfg: Config, llm: JSONModel, draft: dict[str, Any], topic: dict[str, Any]) -> dict[str, Any]:
    """Senior-editor pass: fact-safety, depth, scannability. Also upgrades old-format articles."""
    catalog = "\n".join(f"- {a.name} ({a.category}): {a.blurb}" for a in cfg.affiliates)
    prompt = f"""You are the senior editor of "{cfg.site_name}". Rewrite the draft below into the best
article on the web for the keyword "{topic['keyword']}".

Editing checklist:
1. Remove or soften anything unverifiable (specific prices, statistics, release dates, quotes).
2. Add missing practical depth: exact steps, settings, templates, pitfalls, examples.
3. Make it scannable: strong section openers, short paragraphs, bullets where they help.
4. Fill every field in the field guide (the draft may be missing some).
5. Keep recommendations honest and only from this catalog:
{catalog}

{_ARTICLE_FIELDS_GUIDE}
{_lang_line(cfg)}

DRAFT (JSON):
{json.dumps(draft, ensure_ascii=False)}"""
    return _finish(cfg, llm.generate_json(EDITORIAL_RULES, prompt, article_schema(cfg)), topic)


def write_article(cfg: Config, llm: JSONModel, topic: dict[str, Any]) -> dict[str, Any]:
    catalog = "\n".join(f"- {a.name} ({a.category}): {a.blurb}" for a in cfg.affiliates)
    prompt = f"""Write a complete, publish-ready article for "{cfg.site_name}".

Target keyword: {topic['keyword']}
Working title: {topic['title']}
Angle: {topic['angle']}
Search intent: {topic['search_intent']}

{_ARTICLE_FIELDS_GUIDE}
- recommendations: 0–3 tools, ONLY from this partner catalog and only where they genuinely fit:
{catalog}
{_lang_line(cfg)}"""
    art = _finish(cfg, llm.generate_json(EDITORIAL_RULES, prompt, article_schema(cfg)), topic)
    if cfg.editor_pass:
        art = edit_article(cfg, llm, art, topic)
    return art


# ---------------------------------------------------------------------------
# 3. Digital products (paid guides / playbooks)
# ---------------------------------------------------------------------------
PRODUCT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "audience": {"type": "string"},
        "outcomes": {"type": "array", "items": {"type": "string"}},
        "sales_copy": {"type": "string"},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "summary": {"type": "string"},
                    "paragraphs": {"type": "array", "items": {"type": "string"}},
                    "checklist": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heading", "summary", "paragraphs", "checklist"],
                "additionalProperties": False,
            },
        },
        "templates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "body": {"type": "string"}},
                "required": ["name", "body"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "subtitle", "audience", "outcomes", "sales_copy", "chapters", "templates"],
    "additionalProperties": False,
}


def create_product(cfg: Config, llm: JSONModel, articles: list[dict[str, Any]], products: list[dict[str, Any]]) -> dict[str, Any]:
    popular = "\n".join(f"- {a['title']}" for a in articles[:40]) or "(no articles yet)"
    have = "\n".join(f"- {p['title']}" for p in products) or "(none yet)"
    prompt = f"""Create a premium digital product (a practical playbook) for "{cfg.site_name}" readers,
to sell for about {cfg.default_price}.

Our audience reads articles like:
{popular}

Existing products (make something clearly different):
{have}

Requirements:
- A specific, high-value outcome (e.g. a ready-to-use system, prompt pack, SOP or template kit).
- 6–10 chapters with detailed, actionable paragraphs and a checklist each.
- 5–15 copy-paste templates/prompts in `templates`.
- sales_copy: honest, benefit-led, 120–200 words, no hype or income claims.
{_lang_line(cfg)}"""
    return llm.generate_json(EDITORIAL_RULES, prompt, PRODUCT_SCHEMA)


def product_markdown(product: dict[str, Any]) -> str:
    """Render the full paid deliverable as Markdown (upload to Gumroad / attach to Stripe receipt)."""
    out = [f"# {product['title']}", f"_{product['subtitle']}_", "", f"**For:** {product['audience']}", "",
           "## What you'll achieve", *[f"- {o}" for o in product["outcomes"]], ""]
    for i, ch in enumerate(product["chapters"], 1):
        out += [f"## {i}. {ch['heading']}", "", *[p + "\n" for p in ch["paragraphs"]], "**Checklist**",
                *[f"- [ ] {c}" for c in ch["checklist"]], ""]
    if product["templates"]:
        out += ["## Templates", ""]
        for t in product["templates"]:
            out += [f"### {t['name']}", "", "```", t["body"], "```", ""]
    return "\n".join(out)
