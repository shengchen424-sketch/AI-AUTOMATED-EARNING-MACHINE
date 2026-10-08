"""The autopilot: plan -> write -> productise -> build site -> track revenue."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import generate, pdf, revenue, site
from .config import Config
from .llm import JSONModel, LLMError
from .store import Store, utcnow

log = logging.getLogger("earnbot")


def _product_preview(product: dict[str, Any]) -> dict[str, Any]:
    """Public part of a product: the sales page. Full content stays out of the public repo/site."""
    return {
        "title": product["title"],
        "subtitle": product["subtitle"],
        "audience": product["audience"],
        "outcomes": product["outcomes"],
        "sales_copy": product["sales_copy"],
        "chapters": [{"heading": c["heading"], "summary": c["summary"]} for c in product["chapters"]],
        "template_count": len(product["templates"]),
        "section": product.get("section", ""),
    }


def run(cfg: Config, llm: JSONModel | None, deliverables_dir: Path | None = None) -> dict[str, Any]:
    store = Store(cfg.content_dir, cfg.data_dir)
    report: dict[str, Any] = {"started": utcnow().isoformat(timespec="seconds"),
                              "articles": [], "products": [], "errors": []}

    if llm is None:
        log.warning("Claude CLI not available or not logged in: skipping generation, rebuilding site only.")
        report["errors"].append("no_credentials")
    else:
        existing = store.articles()
        try:
            topics = generate.plan_topics(cfg, llm, existing, cfg.articles_per_run)
        except LLMError as e:
            topics = []
            report["errors"].append(f"plan: {e}")
        for topic in topics:
            try:
                art = store.save_article(generate.write_article(cfg, llm, topic))
                report["articles"].append(art["slug"])
                log.info("published article %s", art["slug"])
            except LLMError as e:
                report["errors"].append(f"article '{topic['title']}': {e}")

        # Re-edit older articles into the newest, richer format (same URL, fresher content).
        stale = [a for a in store.articles() if a.get("version", 1) < generate.ARTICLE_VERSION]
        for old in stale[: cfg.upgrades_per_run]:
            topic = {"keyword": old.get("keyword", old["title"]), "niche": old.get("niche", "")}
            try:
                new = generate.edit_article(cfg, llm, old, topic)
            except LLMError as e:
                report["errors"].append(f"upgrade '{old['slug']}': {e}")
                continue
            new.update(slug=old["slug"], published=old["published"])
            store.update_article(new)
            report.setdefault("upgraded", []).append(old["slug"])
            log.info("upgraded article %s", old["slug"])

        products = store.products()
        for _ in range(cfg.products_per_run):
            if len(products) >= cfg.max_products:
                break
            try:
                full = generate.create_product(cfg, llm, store.articles(), products)
            except LLMError as e:
                report["errors"].append(f"product: {e}")
                break
            saved = store.save_product(_product_preview(full))
            if deliverables_dir:
                deliverables_dir.mkdir(parents=True, exist_ok=True)
                (deliverables_dir / f"{saved['slug']}.md").write_text(
                    generate.product_markdown(full), encoding="utf-8")
                html = pdf.product_html(full, cfg.business_name)
                (deliverables_dir / f"{saved['slug']}.html").write_text(html, encoding="utf-8")
                pdf.html_to_pdf(html, (deliverables_dir / f"{saved['slug']}.pdf").resolve())
            report["products"].append(saved["slug"])
            products = store.products()
            log.info("created product %s", saved["slug"])

    try:
        rev = revenue.stripe_report()
        if rev:
            store.save_revenue(rev)
            report["revenue"] = rev
    except OSError as e:  # network/HTTP errors must never block publishing
        report["errors"].append(f"revenue: {e}")

    report["site"] = site.build(cfg, store)
    report["finished"] = utcnow().isoformat(timespec="seconds")
    store.log_run(report)
    return report
