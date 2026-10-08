"""Render the static, SEO + AI-answer-engine ready, monetised website into public/."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import ogimage
from .tools import TOOLS
from .config import Config
from .store import Store, slugify, utcnow

# Crawlers we explicitly welcome: search engines plus the AI assistants / answer engines
# that cite web pages (ChatGPT, Claude, Perplexity, Gemini, Copilot, Apple, Meta, etc.).
AI_CRAWLERS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot",
    "anthropic-ai", "PerplexityBot", "Perplexity-User", "Google-Extended", "Googlebot", "Bingbot",
    "Applebot", "Applebot-Extended", "Meta-ExternalAgent", "Amazonbot", "DuckAssistBot",
    "CCBot", "cohere-ai", "MistralAI-User", "YouBot",
]


def indexnow_key(cfg: Config) -> str:
    return hashlib.sha256(cfg.base_url.encode()).hexdigest()[:32]


def _env(cfg: Config) -> Environment:
    env = Environment(loader=FileSystemLoader(cfg.root / "templates"), autoescape=select_autoescape(["html"]))
    css = (cfg.root / "templates" / "style.css").read_bytes()
    env.globals.update(cfg=cfg, year=utcnow().year, today=utcnow().strftime("%B %Y"),
                       css_version=hashlib.md5(css).hexdigest()[:8])
    return env


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ld(data: dict[str, Any]) -> str:
    # Escape "<" so content can never close the surrounding <script> tag.
    return json.dumps({"@context": "https://schema.org", **data}, ensure_ascii=False).replace("<", "\\u003c")


def _page(cfg: Config, title: str, description: str, path: str, **extra: Any) -> dict[str, Any]:
    page = {"title": title, "description": description, "path": path, "jsonld": [], **extra}
    page["jsonld"].insert(0, _ld({
        "@type": "WebSite", "name": cfg.site_name, "url": f"{cfg.base_url}/", "description": cfg.tagline,
        "publisher": {"@type": "Organization", "name": cfg.business_name, "url": f"{cfg.base_url}/"},
    }))
    return page


def _breadcrumb(cfg: Config, trail: list[tuple[str, str]]) -> str:
    return _ld({"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": f"{cfg.base_url}/{path}"}
        for i, (name, path) in enumerate(trail, 1)]})


# ---------------------------------------------------------------------------
# Article helpers
# ---------------------------------------------------------------------------
def _words(a: dict[str, Any]) -> int:
    parts = [a.get("intro", ""), a.get("quick_answer", ""), a.get("conclusion", "")]
    parts += [p for s in a.get("sections", []) for p in s["paragraphs"] + s["bullets"]]
    parts += [s["text"] for s in a.get("steps", [])] + [f["answer"] for f in a.get("faq", [])]
    return sum(len(p.split()) for p in parts)


def _decorate(cfg: Config, articles: list[dict[str, Any]]) -> None:
    for a in articles:
        a["reading_minutes"] = max(1, round(_words(a) / 220))
        niche = a.get("niche", "")
        a["niche_slug"] = slugify(niche) if niche else ""
        a["niche_label"] = niche[:1].upper() + niche[1:] if niche else ""
        info = cfg.niche(niche)
        a["care"], a["section"] = info.care, info.section


def article_markdown(cfg: Config, a: dict[str, Any]) -> str:
    """Clean Markdown version of an article: what LLM crawlers and llms-full.txt consume."""
    url = f"{cfg.base_url}/{a['slug']}/"
    out = [f"# {a['title']}", "", f"Source: {url}", f"Published: {a['published'][:10]}"
           + (f" · Updated: {a['updated'][:10]}" if a.get("updated") else ""), ""]
    if a.get("quick_answer"):
        out += ["## Quick answer", "", a["quick_answer"], ""]
    if a.get("key_takeaways"):
        out += ["## Key takeaways", "", *[f"- {k}" for k in a["key_takeaways"]], ""]
    out += [a.get("intro", ""), ""]
    if a.get("steps"):
        out += ["## Step-by-step", "", *[f"{i}. **{s['name']}** — {s['text']}" for i, s in enumerate(a["steps"], 1)], ""]
    comp = a.get("comparison") or {}
    for i, s in enumerate(a.get("sections", []), 1):
        out += [f"## {s['heading']}", "", *[p + "\n" for p in s["paragraphs"]], *[f"- {b}" for b in s["bullets"]], ""]
        if i == 1 and comp.get("rows"):
            out += [f"**{comp['caption']}**" if comp.get("caption") else "", "",
                    "| " + " | ".join(comp["headers"]) + " |", "|" + "---|" * len(comp["headers"]),
                    *["| " + " | ".join(r) + " |" for r in comp["rows"]], ""]
    if a.get("faq"):
        out += ["## FAQ", ""]
        for f in a["faq"]:
            out += [f"### {f['question']}", "", f["answer"], ""]
    out += ["## Bottom line", "", a.get("conclusion", ""), ""]
    return "\n".join(out)


def _article_ld(cfg: Config, a: dict[str, Any]) -> list[str]:
    url = f"{cfg.base_url}/{a['slug']}/"
    blocks = [_ld({
        "@type": "Article", "headline": a["title"], "description": a["meta_description"],
        "image": f"{cfg.base_url}/assets/og/{a['slug']}.png",
        "datePublished": a["published"], "dateModified": a.get("updated") or a["published"],
        "author": {"@type": "Organization", "name": cfg.author, "url": f"{cfg.base_url}/about/"},
        "publisher": {"@type": "Organization", "name": cfg.business_name},
        "mainEntityOfPage": url, "wordCount": _words(a), "keywords": a.get("keyword", ""),
        "articleSection": a.get("niche_label", ""),
        **({"abstract": a["quick_answer"]} if a.get("quick_answer") else {}),
    })]
    if a.get("faq"):
        blocks.append(_ld({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["question"], "acceptedAnswer": {"@type": "Answer", "text": f["answer"]}}
            for f in a["faq"]]}))
    if a.get("steps"):
        blocks.append(_ld({"@type": "HowTo", "name": a["title"], "description": a.get("quick_answer", a["meta_description"]),
                           "step": [{"@type": "HowToStep", "position": i, "name": s["name"], "text": s["text"]}
                                    for i, s in enumerate(a["steps"], 1)]}))
    trail = [("Home", "")]
    if a.get("niche_slug"):
        trail.append((a["niche_label"], f"topics/{a['niche_slug']}/"))
    blocks.append(_breadcrumb(cfg, trail + [(a["title"], f"{a['slug']}/")]))
    return blocks


def _related(a: dict[str, Any], articles: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    others = [x for x in articles if x["slug"] != a["slug"]]
    same = [x for x in others if x.get("niche") == a.get("niche")]
    return (same + [x for x in others if x not in same])[:n]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def build(cfg: Config, store: Store) -> dict[str, int]:
    out = cfg.public_dir
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    env = _env(cfg)
    articles, products, glossary = store.articles(), store.products(), store.glossary()
    _decorate(cfg, articles)
    for x in glossary:
        x["care"] = "finance" if x.get("section") in {n.section for n in cfg.niches if n.care == "finance"} else ""
    term_by_slug = {x["slug"]: x for x in glossary}
    article_text = {a["slug"]: article_markdown(cfg, a).lower() for a in articles}

    def terms_in(slug: str) -> list[dict[str, Any]]:
        text = article_text[slug]
        return [x for x in glossary if len(x["term"]) > 2 and x["term"].lower() in text][:10]
    price = cfg.default_price
    common = {"products": products, "checkout_links": cfg.checkout_links, "price": price}

    topics_map: dict[str, dict[str, Any]] = {}
    for a in articles:
        if a["niche_slug"]:
            t = topics_map.setdefault(a["niche_slug"], {"slug": a["niche_slug"], "label": a["niche_label"],
                                                        "section": a["section"], "items": []})
            t["items"].append(a)
    topics = sorted(({**t, "count": len(t["items"])} for t in topics_map.values()), key=lambda t: -t["count"])
    section_order = list(dict.fromkeys(n.section for n in cfg.niches))
    sections = [{"name": s, "topics": [t for t in topics if t["section"] == s]} for s in section_order]
    sections = [s for s in sections if s["topics"]] + (
        [{"name": "More", "topics": [t for t in topics if t["section"] not in section_order]}]
        if any(t["section"] not in section_order for t in topics) else [])

    # assets: stylesheet + social cards
    (out / "assets").mkdir()
    shutil.copy(cfg.root / "templates" / "style.css", out / "assets" / "style.css")
    ogimage.render(out / "assets" / "og" / "site.png", cfg.site_name, cfg.tagline, cfg.site_name)
    for a in articles:
        ogimage.render(out / "assets" / "og" / f"{a['slug']}.png", a["title"], a.get("niche_label", ""), cfg.site_name)
        ogimage.render_pin(out / "assets" / "pins" / f"{a['slug']}.png", a["title"], a.get("section", ""), cfg.site_name)

    def render(path: str, template: str, page: dict[str, Any], **ctx: Any) -> None:
        _write(out / path / "index.html" if path else out / "index.html",
               env.get_template(template).render(page=page, **common, **ctx))

    home = _page(cfg, f"{cfg.site_name} — {cfg.tagline}", cfg.tagline, "")
    home["jsonld"].append(_ld({"@type": "Organization", "name": cfg.business_name, "url": f"{cfg.base_url}/",
                               "logo": f"{cfg.base_url}/assets/og/site.png", "description": cfg.tagline,
                               **({"email": cfg.contact_email} if cfg.contact_email else {})}))
    render("", "index.html", home, articles=articles, topics=topics, sections=sections, tools=TOOLS,
           glossary=sorted(glossary, key=lambda x: x.get("published", ""), reverse=True))

    render("guides", "listing.html",
           _page(cfg, f"All guides — {cfg.site_name}", f"Every {cfg.site_name} guide: practical, step-by-step answers on money, family, learning and AI.", "guides/"),
           heading="All guides", intro="Practical, step-by-step guides on money, family, learning and AI — newest first.", items=articles, topics=topics)
    render("topics", "listing.html",
           _page(cfg, f"Topics — {cfg.site_name}", "Browse guides by topic.", "topics/"),
           heading="Browse by topic", intro="Pick a topic to see every guide we've written on it.", items=articles, sections=sections)
    for t in topics:
        page = _page(cfg, f"{t['label']}: guides — {cfg.site_name}", f"Practical guides on {t['label'].lower()}.", f"topics/{t['slug']}/")
        page["jsonld"].append(_breadcrumb(cfg, [("Home", ""), ("Topics", "topics/"), (t["label"], f"topics/{t['slug']}/")]))
        render(f"topics/{t['slug']}", "listing.html", page, heading=t["label"],
               intro=f"{t['count']} practical guide{'s' if t['count'] != 1 else ''} on {t['label'].lower()}.", items=t["items"], crumb=True)

    for i, a in enumerate(articles):
        recs = [dict(r, aff=aff) for r in a.get("recommendations", []) if (aff := cfg.affiliate(r["product"]))]
        product = products[i % len(products)] if products else None
        page = _page(cfg, f"{a['title']} — {cfg.site_name}", a["meta_description"], f"{a['slug']}/",
                     og_type="article", og_image=f"assets/og/{a['slug']}.png", published=a["published"],
                     modified=a.get("updated") or a["published"], markdown=f"{a['slug']}/index.md")
        page["jsonld"] += _article_ld(cfg, a)
        render(a["slug"], "article.html", page, a=a, recs=recs, product=product, related=_related(a, articles),
               key_terms=terms_in(a["slug"]))
        _write(out / a["slug"] / "index.md", article_markdown(cfg, a))

    # Free calculators: link magnets for people, quotable explainers for AI assistants.
    render("tools", "tools.html", _page(cfg, f"Free money calculators — {cfg.site_name}",
           "Free compound interest, ETF/DCA, debt payoff, emergency fund and FIRE calculators.", "tools/"), tools=TOOLS)
    for tool in TOOLS:
        path = f"tools/{tool['slug']}/"
        page = _page(cfg, f"{tool['title']} (Free) — {cfg.site_name}", tool["summary"], path)
        page["jsonld"] += [
            _ld({"@type": "WebApplication", "name": tool["title"], "description": tool["summary"],
                 "url": f"{cfg.base_url}/{path}", "applicationCategory": "FinanceApplication",
                 "operatingSystem": "Any", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}}),
            _ld({"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in tool["explain"] + tool["faq"]]}),
            _breadcrumb(cfg, [("Home", ""), ("Free tools", "tools/"), (tool["title"], path)]),
        ]
        words = tool["match"]
        related = [a for a in articles if any(w in (a["title"] + " " + a.get("keyword", "")).lower() for w in words)][:5]
        render(path.rstrip("/"), "tool.html", page, t=tool, tools=TOOLS, related=related,
               ids=json.dumps([i[0] for i in tool["inputs"]]))

    # Glossary: A–Z index + one page per term (DefinedTerm), cross-linked with articles.
    groups: dict[str, list[dict[str, Any]]] = {}
    for x in glossary:
        first = x["term"][:1].upper()
        groups.setdefault(first if first.isalpha() else "#", []).append(x)
    gpage = _page(cfg, f"Money, investing & AI glossary — {cfg.site_name}",
                  "Plain-English definitions of investing, banking, accounting and AI terms, with examples.", "glossary/")
    gpage["jsonld"].append(_ld({"@type": "DefinedTermSet", "name": f"{cfg.site_name} Glossary", "url": f"{cfg.base_url}/glossary/",
                                "hasDefinedTerm": [{"@type": "DefinedTerm", "name": x["term"], "description": x["short_definition"],
                                                    "url": f"{cfg.base_url}/glossary/{x['slug']}/"} for x in glossary]}))
    render("glossary", "glossary.html", gpage, terms=glossary, groups=sorted(groups.items()))
    for x in glossary:
        path = f"glossary/{x['slug']}/"
        page = _page(cfg, f"What is {x['term']}? Definition & example — {cfg.site_name}", x["short_definition"], path)
        page["jsonld"] += [
            _ld({"@type": "DefinedTerm", "name": x["term"], "description": x["short_definition"], "url": f"{cfg.base_url}/{path}",
                 "inDefinedTermSet": f"{cfg.base_url}/glossary/"}),
            _ld({"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": f"What is {x['term']}?",
                 "acceptedAnswer": {"@type": "Answer", "text": " ".join([x["short_definition"], *x["explanation"]])}}]}),
            _breadcrumb(cfg, [("Home", ""), ("Glossary", "glossary/"), (x["term"], path)]),
        ]
        related_terms = [term_by_slug[s] for s in dict.fromkeys(slugify(r) for r in x["related_terms"])
                         if s in term_by_slug and s != x["slug"]]
        using = [a for a in articles if x["term"].lower() in article_text[a["slug"]]][:6]
        render(path.rstrip("/"), "term.html", page, x=x, related_terms=related_terms, articles=using)

    render("products", "products.html", _page(cfg, f"Playbooks — {cfg.site_name}", "Done-for-you AI playbooks with copy-paste templates.", "products/"))
    for p in products:
        checkout = cfg.checkout_links.get(p["slug"])
        page = _page(cfg, f"{p['title']} — {cfg.site_name}", p["subtitle"], f"products/{p['slug']}/")
        amount = "".join(ch for ch in price if ch.isdigit() or ch == ".")
        product_ld: dict[str, Any] = {"@type": "Product", "name": p["title"], "description": p["subtitle"],
                                      "brand": {"@type": "Brand", "name": cfg.site_name},
                                      "image": f"{cfg.base_url}/assets/og/site.png"}
        if checkout and amount:
            product_ld["offers"] = {"@type": "Offer", "price": amount, "priceCurrency": "USD" if "$" in price else "MYR",
                                    "availability": "https://schema.org/InStock", "url": f"{cfg.base_url}/products/{p['slug']}/"}
        page["jsonld"] += [_ld(product_ld), _breadcrumb(cfg, [("Home", ""), ("Playbooks", "products/"), (p["title"], f"products/{p['slug']}/")])]
        render(f"products/{p['slug']}", "product.html", page, p=p, checkout=checkout)

    static_pages = [("about", "about.html", f"About {cfg.site_name}"), ("contact", "contact.html", "Contact us"),
                    ("refund-policy", "refund.html", "Refund policy"), ("terms", "terms.html", "Terms of service"),
                    ("privacy", "privacy.html", "Privacy policy")]
    for path, tpl, title in static_pages:
        render(path, tpl, _page(cfg, f"{title} — {cfg.site_name}", f"{title} for {cfg.site_name}.", f"{path}/"))
    _write(out / "404.html", env.get_template("notfound.html").render(page=_page(cfg, f"Not found — {cfg.site_name}", "Page not found.", "404.html"), **common))

    urls = [("", None), ("guides/", None), ("topics/", None), ("products/", None)]
    urls += [(f"topics/{t['slug']}/", None) for t in topics]
    urls += [("tools/", None)] + [(f"tools/{tool['slug']}/", None) for tool in TOOLS]
    urls += [("glossary/", None)] + [(f"glossary/{x['slug']}/", x["published"]) for x in glossary]
    urls += [(f"{a['slug']}/", a.get("updated") or a["published"]) for a in articles]
    urls += [(f"products/{p['slug']}/", p["published"]) for p in products]
    urls += [(f"{path}/", None) for path, _, _ in static_pages]
    _write(out / "sitemap.xml", _sitemap(cfg, urls))
    _write(out / "robots.txt", _robots(cfg))
    _write(out / "feed.xml", _rss(cfg, articles[:30]))
    _write(out / "feed.json", json.dumps({
        "version": "https://jsonfeed.org/version/1.1", "title": cfg.site_name, "home_page_url": f"{cfg.base_url}/",
        "feed_url": f"{cfg.base_url}/feed.json", "description": cfg.tagline,
        "items": [{"id": f"{cfg.base_url}/{a['slug']}/", "url": f"{cfg.base_url}/{a['slug']}/", "title": a["title"],
                   "summary": a.get("quick_answer") or a["meta_description"], "content_text": article_markdown(cfg, a),
                   "image": f"{cfg.base_url}/assets/og/{a['slug']}.png", "date_published": a["published"],
                   "date_modified": a.get("updated") or a["published"], "tags": [a.get("section", "")]}
                  for a in articles[:30]]}, ensure_ascii=False, indent=1))
    _write(out / "llms.txt", _llms(cfg, articles, products, topics, glossary))
    _write(out / "llms-full.txt", "\n\n---\n\n".join([article_markdown(cfg, a) for a in articles] + [_glossary_markdown(cfg, glossary)]))
    _write(out / f"{indexnow_key(cfg)}.txt", indexnow_key(cfg))
    _write(out / ".nojekyll", "")
    # Verification files and other static assets that must sit at the site root.
    static = cfg.root / "static"
    if static.is_dir():
        shutil.copytree(static, out, dirs_exist_ok=True)
    return {"articles": len(articles), "products": len(products), "topics": len(topics), "pages": len(urls)}


def _robots(cfg: Config) -> str:
    groups = "".join(f"User-agent: {bot}\nAllow: /\n\n" for bot in AI_CRAWLERS)
    return f"{groups}User-agent: *\nAllow: /\n\nSitemap: {cfg.base_url}/sitemap.xml\n"


def _glossary_markdown(cfg: Config, glossary: list[dict[str, Any]]) -> str:
    out = [f"# {cfg.site_name} Glossary", "", f"Source: {cfg.base_url}/glossary/", ""]
    for x in glossary:
        out += [f"## {x['term']}", "", x["short_definition"], "", *x["explanation"], "", f"Example: {x['example']}", ""]
    return "\n".join(out)


def _llms(cfg: Config, articles: list[dict[str, Any]], products: list[dict[str, Any]], topics: list[dict[str, Any]],
          glossary: list[dict[str, Any]] | None = None) -> str:
    """llms.txt (llmstxt.org): a curated, Markdown map of the site for AI assistants."""
    out = [f"# {cfg.site_name}", "", f"> {cfg.tagline}", "",
           "Practical, step-by-step guides on personal finance, parenting, kids' education and AI tools. Every guide starts with a "
           "direct quick answer, then numbered steps, comparisons and FAQs. We do not publish invented "
           "statistics or prices. Each guide is also available as Markdown at <guide-url>index.md, and the "
           f"full text of all guides is at {cfg.base_url}/llms-full.txt.", ""]
    for t in topics:
        out += [f"## {t['label']}", ""]
        out += [f"- [{a['title']}]({cfg.base_url}/{a['slug']}/index.md): {a.get('quick_answer') or a['meta_description']}"
                for a in t["items"]]
        out.append("")
    untopiced = [a for a in articles if not a.get("niche_slug")]
    if untopiced:
        out += ["## Guides", "", *[f"- [{a['title']}]({cfg.base_url}/{a['slug']}/index.md): {a['meta_description']}" for a in untopiced], ""]
    if glossary:
        out += ["## Glossary", "", *[f"- [{x['term']}]({cfg.base_url}/glossary/{x['slug']}/): {x['short_definition']}" for x in glossary], ""]
    out += ["## Free calculators", "", *[f"- [{tool['title']}]({cfg.base_url}/tools/{tool['slug']}/): {tool['summary']}" for tool in TOOLS], ""]
    if products:
        out += ["## Playbooks", "", *[f"- [{p['title']}]({cfg.base_url}/products/{p['slug']}/): {p['subtitle']}" for p in products], ""]
    out += ["## Optional", "", f"- [About and editorial policy]({cfg.base_url}/about/)", f"- [RSS feed]({cfg.base_url}/feed.xml)", ""]
    return "\n".join(out)


def _sitemap(cfg: Config, urls: list[tuple[str, str | None]]) -> str:
    rows = []
    for path, lastmod in urls:
        mod = f"<lastmod>{lastmod[:10]}</lastmod>" if lastmod else ""
        rows.append(f"<url><loc>{escape(cfg.base_url + '/' + path)}</loc>{mod}</url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(rows) + "\n</urlset>\n")


def _rss(cfg: Config, articles: list[dict[str, Any]]) -> str:
    items = []
    for a in articles:
        link = f"{cfg.base_url}/{a['slug']}/"
        date = format_datetime(datetime.fromisoformat(a["published"]))
        desc = a.get("quick_answer") or a["meta_description"]
        items.append(f"<item><title>{escape(a['title'])}</title><link>{escape(link)}</link>"
                     f"<guid>{escape(link)}</guid><pubDate>{date}</pubDate>"
                     f"<description>{escape(desc)}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f"<title>{escape(cfg.site_name)}</title><link>{escape(cfg.base_url)}/</link>"
            f"<description>{escape(cfg.tagline)}</description>" + "".join(items) + "</channel></rss>\n")
