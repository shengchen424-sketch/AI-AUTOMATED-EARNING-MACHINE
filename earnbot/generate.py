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
- Write in plain, friendly, expert language for busy, practical readers.

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


CARE_RULES = {
    "finance": """Money topic (YMYL) — extra rules:
- Educate, don't advise: explain concepts, trade-offs and how to decide; never tell the reader to buy,
  sell or hold a specific stock, coin, ETF or fund, never give price targets, and never promise returns.
- Name well-known products/assets only as neutral examples of a category, with their key risks.
- Crypto: stress volatility, the possibility of total loss, scams/rug pulls, custody and exchange risk,
  and that protections differ from regulated bank deposits.
- Mention risk, fees and that rules/tax treatment differ by country; tell readers to check their
  local regulator or a licensed adviser for personal decisions.
- No specific interest rates, returns or tax thresholds unless clearly labelled as examples.""",
    "health": """Baby/child health topic (YMYL) — extra rules:
- Follow mainstream guidance from bodies like the WHO and national paediatric associations; if
  guidance varies or is uncertain, say so.
- Never give medication doses, diagnoses or treatment plans. Clearly list warning signs that need
  a doctor, and say when to call emergency services.
- Safety first: safe-sleep, car-seat and feeding safety must match mainstream guidance.
- Tell parents to check with their paediatrician or health visitor for their own child.""",
}


def care_rules(cfg: Config, niche: str) -> str:
    return CARE_RULES.get(cfg.niche(niche).care, "")


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


def pick_niches(cfg: Config, existing: list[dict[str, Any]], count: int) -> list[str]:
    """Least-covered niches first, so the site grows evenly across every category."""
    active = [n for n in cfg.niches if n.active]
    counts = {n.name: 0 for n in active}
    for a in existing:
        if a.get("niche") in counts:
            counts[a["niche"]] += 1
    order = sorted(active, key=lambda n: (counts[n.name], active.index(n)))
    return [n.name for n in order[:count]]


def plan_topics(cfg: Config, llm: JSONModel, existing: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    covered = "\n".join(f"- {a['title']} [{a.get('keyword', '')}]" for a in existing[:300]) or "(none yet)"
    targets = pick_niches(cfg, existing, count)
    schema = json.loads(json.dumps(TOPICS_SCHEMA))
    schema["properties"]["topics"]["items"]["properties"]["niche"] = {"type": "string", "enum": targets}
    prompt = f"""You are the editor-in-chief and SEO strategist of "{cfg.site_name}" — {cfg.tagline}

This run, write ONE topic for EACH of these niches (use the niche text exactly), plus up to 3 spares:
{chr(10).join('- ' + n for n in targets)}

Already published (do NOT repeat or closely overlap):
{covered}

Favour specific long-tail questions real people search for, that a new site can rank for and that
AI assistants get asked. Where one of our partner tools genuinely fits, prefer that angle:
{', '.join(a.name for a in cfg.affiliates)}. {_lang_line(cfg)}"""
    data = llm.generate_json(EDITORIAL_RULES, prompt, schema)
    seen = {slugify(a["title"]) for a in existing} | {slugify(a.get("keyword", "")) for a in existing}
    picked: list[dict[str, Any]] = []
    used: set[str] = set()
    # First pass: one topic per target niche; second pass: fill from spares.
    for strict in (True, False):
        for t in data["topics"]:
            key, kw = slugify(t["title"]), slugify(t["keyword"])
            if len(picked) == count or key in seen or kw in seen or (strict and t["niche"] in used):
                continue
            seen |= {key, kw}
            used.add(t["niche"])
            picked.append(t)
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
{care_rules(cfg, topic.get('niche', ''))}
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
- recommendations: 0–3 tools, ONLY from this partner catalog and only where they genuinely fit
  (an empty list is fine and expected for topics where none of them fit):
{catalog}
{care_rules(cfg, topic['niche'])}
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


# ---------------------------------------------------------------------------
# 2b. Glossary (definitions are what AI assistants quote most)
# ---------------------------------------------------------------------------
def glossary_schema(cfg: Config) -> dict[str, Any]:
    sections = list(dict.fromkeys(n.section for n in cfg.niches if n.active)) or ["Guides"]
    return {
        "type": "object",
        "properties": {"terms": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "section": {"type": "string", "enum": sections},
                "short_definition": {"type": "string"},
                "explanation": {"type": "array", "items": {"type": "string"}},
                "example": {"type": "string"},
                "common_mistake": {"type": "string"},
                "related_terms": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["term", "section", "short_definition", "explanation", "example", "common_mistake", "related_terms"],
            "additionalProperties": False,
        }}},
        "required": ["terms"],
        "additionalProperties": False,
    }


def write_glossary_terms(cfg: Config, llm: JSONModel, existing: list[str], count: int) -> list[dict[str, Any]]:
    sections = list(dict.fromkeys(n.section for n in cfg.niches if n.active))
    prompt = f"""Add {count} new entries to the "{cfg.site_name}" glossary — the terms beginners actually
search for ("what is ...") across: {', '.join(sections)}. Spread them across sections.

Already defined (do NOT repeat): {', '.join(existing[:500]) or '(none yet)'}

For each term:
- short_definition: one self-contained sentence of 15–35 words that AI assistants can quote verbatim.
- explanation: 2–3 short paragraphs: how it works, why it matters, and the main trade-off or risk.
- example: a concrete worked example with simple illustrative numbers (label them as an example).
- common_mistake: one mistake beginners make with it.
- related_terms: 2–5 closely related glossary terms.
{CARE_RULES['finance']}
{_lang_line(cfg)}"""
    data = llm.generate_json(EDITORIAL_RULES, prompt, glossary_schema(cfg))
    seen = {slugify(x) for x in existing}
    fresh = []
    for term in data["terms"]:
        if slugify(term["term"]) not in seen:
            seen.add(slugify(term["term"]))
            fresh.append(term)
    return fresh


# ---------------------------------------------------------------------------
# 2c. Social promotion kit (the owner posts these; nothing is auto-spammed)
# ---------------------------------------------------------------------------
SOCIAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "x_thread": {"type": "array", "items": {"type": "string"}},
        "linkedin_post": {"type": "string"},
        "facebook_post": {"type": "string"},
        "reddit_title": {"type": "string"},
        "reddit_post": {"type": "string"},
        "suggested_subreddits": {"type": "array", "items": {"type": "string"}},
        "pinterest_title": {"type": "string"},
        "pinterest_description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["x_thread", "linkedin_post", "facebook_post", "reddit_title", "reddit_post",
                 "suggested_subreddits", "pinterest_title", "pinterest_description", "hashtags"],
    "additionalProperties": False,
}


def social_kit(cfg: Config, llm: JSONModel, article: dict[str, Any]) -> dict[str, Any]:
    summary = {k: article.get(k) for k in ("title", "quick_answer", "key_takeaways", "steps", "faq")}
    prompt = f"""Write a social media promotion kit for this "{cfg.site_name}" article. Use {{URL}} where the
link goes (it will be replaced with a tracked link). Lead with genuine value so people engage even
without clicking; no clickbait, no income promises, no "not financial advice" boilerplate in the hook.

- x_thread: 4–6 posts, each under 260 characters; post 1 is a strong hook; the link goes in the last post.
- linkedin_post: 120–200 words, professional, short paragraphs, link at the end.
- facebook_post: 60–120 words, friendly, suited to personal-finance / money groups, link at the end.
- reddit_title + reddit_post: a value-first text post that fully answers the question in the post itself
  (Reddit dislikes self-promotion); mention the full guide link once at the end, transparently.
- suggested_subreddits: 3–5 relevant subreddits (e.g. r/personalfinance, r/financialindependence, r/ETFs);
  the owner must check each subreddit's self-promotion rules before posting.
- pinterest_title (under 100 chars) + pinterest_description (2–3 sentences with keywords).
- hashtags: 5–8 relevant hashtags without the # sign.
{_lang_line(cfg)}

ARTICLE (JSON):
{json.dumps(summary, ensure_ascii=False)}"""
    return llm.generate_json(EDITORIAL_RULES, prompt, SOCIAL_SCHEMA)


def pick_section(cfg: Config, articles: list[dict[str, Any]], products: list[dict[str, Any]]) -> str:
    """Section with the fewest playbooks (ties: the one with the most articles, i.e. most traffic)."""
    sections = list(dict.fromkeys(n.section for n in cfg.niches if n.active)) or ["Guides"]
    n_prod = {s: sum(p.get("section") == s for p in products) for s in sections}
    n_art = {s: sum(cfg.niche(a.get("niche", "")).section == s for a in articles) for s in sections}
    return min(sections, key=lambda s: (n_prod[s], -n_art[s], sections.index(s)))


def create_product(cfg: Config, llm: JSONModel, articles: list[dict[str, Any]], products: list[dict[str, Any]]) -> dict[str, Any]:
    section = pick_section(cfg, articles, products)
    niches = [n for n in cfg.niches if n.section == section and n.active]
    related = [a for a in articles if cfg.niche(a.get("niche", "")).section == section]
    popular = "\n".join(f"- {a['title']}" for a in (related or articles)[:40]) or "(no articles yet)"
    have = "\n".join(f"- {p['title']}" for p in products) or "(none yet)"
    cares = {n.care for n in niches if n.care}
    prompt = f"""Create a premium digital product (a practical playbook) for "{cfg.site_name}" readers
in our "{section}" section, to sell for about {cfg.default_price}.

Topics in this section: {', '.join(n.name for n in niches)}

Our readers in this section read articles like:
{popular}

Existing products (make something clearly different):
{have}

Requirements:
- A specific, high-value outcome (e.g. a ready-to-use system, planner, checklist kit, prompt pack or SOP).
- 6–10 chapters with detailed, actionable paragraphs and a checklist each.
- 5–15 copy-paste templates/prompts/worksheets in `templates`.
- sales_copy: honest, benefit-led, 120–200 words, no hype, no income or results guarantees.
{chr(10).join(CARE_RULES[c] for c in sorted(cares))}
{_lang_line(cfg)}"""
    product = llm.generate_json(EDITORIAL_RULES, prompt, PRODUCT_SCHEMA)
    product["section"] = section
    return product


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
