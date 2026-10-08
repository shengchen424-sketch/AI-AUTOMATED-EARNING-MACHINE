"""Render the static, SEO-ready, monetised website into public/."""

from __future__ import annotations

import json
import shutil
from email.utils import format_datetime
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Config
from .store import Store, utcnow


def _env(cfg: Config) -> Environment:
    env = Environment(
        loader=FileSystemLoader(cfg.root / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    env.globals.update(cfg=cfg, year=utcnow().year)
    return env


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _article_jsonld(cfg: Config, a: dict[str, Any]) -> str:
    data = [
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": a["title"],
            "description": a["meta_description"],
            "datePublished": a["published"],
            "author": {"@type": "Organization", "name": cfg.author},
            "mainEntityOfPage": f"{cfg.base_url}/{a['slug']}/",
        }
    ]
    if a.get("faq"):
        data.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": f["question"],
                 "acceptedAnswer": {"@type": "Answer", "text": f["answer"]}}
                for f in a["faq"]
            ],
        })
    # Escape "<" so article text can never close the <script> tag.
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def build(cfg: Config, store: Store) -> dict[str, int]:
    out = cfg.public_dir
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    env = _env(cfg)
    articles, products = store.articles(), store.products()

    _write(out / "index.html", env.get_template("index.html").render(articles=articles, products=products))
    _write(out / "about" / "index.html", env.get_template("about.html").render())
    _write(out / "products" / "index.html", env.get_template("products.html").render(products=products))

    tpl = env.get_template("article.html")
    for i, a in enumerate(articles):
        recs = [dict(r, aff=aff) for r in a.get("recommendations", []) if (aff := cfg.affiliate(r["product"]))]
        product = products[i % len(products)] if products else None
        _write(out / a["slug"] / "index.html",
               tpl.render(a=a, recs=recs, product=product, jsonld=_article_jsonld(cfg, a)))

    tpl = env.get_template("product.html")
    for p in products:
        _write(out / "products" / p["slug"] / "index.html",
               tpl.render(p=p, checkout=cfg.checkout_links.get(p["slug"]), price=cfg.default_price))

    urls = [("", None), ("about/", None), ("products/", None)]
    urls += [(f"{a['slug']}/", a["published"]) for a in articles]
    urls += [(f"products/{p['slug']}/", p["published"]) for p in products]
    _write(out / "sitemap.xml", _sitemap(cfg, urls))
    _write(out / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {cfg.base_url}/sitemap.xml\n")
    _write(out / "feed.xml", _rss(cfg, articles[:30]))
    _write(out / ".nojekyll", "")
    _write(out / "404.html", env.get_template("index.html").render(articles=articles[:10], products=products))
    return {"articles": len(articles), "products": len(products), "pages": len(urls)}


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
        items.append(f"<item><title>{escape(a['title'])}</title><link>{escape(link)}</link>"
                     f"<guid>{escape(link)}</guid><pubDate>{date}</pubDate>"
                     f"<description>{escape(a['meta_description'])}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f"<title>{escape(cfg.site_name)}</title><link>{escape(cfg.base_url)}/</link>"
            f"<description>{escape(cfg.tagline)}</description>" + "".join(items) + "</channel></rss>\n")
