"""The autopilot: plan -> write -> productise -> build site -> track revenue."""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
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


def _save_product(cfg: Config, store: Store, full: dict[str, Any], deliverables_dir: Path | None) -> str:
    saved = store.save_product(_product_preview(full))
    if deliverables_dir:
        deliverables_dir.mkdir(parents=True, exist_ok=True)
        (deliverables_dir / f"{saved['slug']}.md").write_text(generate.product_markdown(full), encoding="utf-8")
        html = pdf.product_html(full, cfg.business_name)
        (deliverables_dir / f"{saved['slug']}.html").write_text(html, encoding="utf-8")
        pdf.html_to_pdf(html, (deliverables_dir / f"{saved['slug']}.pdf").resolve())
    return saved["slug"]


def _generate(cfg: Config, llm: JSONModel, store: Store, report: dict[str, Any], deliverables_dir: Path | None) -> None:
    """All model calls run in parallel worker threads; every file write happens on this thread."""
    existing = store.articles()
    products = store.products()
    newest = max((datetime.fromisoformat(x["published"]) for x in products), default=None)
    want_product = (newest is None or utcnow() - newest >= timedelta(hours=cfg.product_interval_hours)) \
        and len(products) < cfg.max_products and cfg.products_per_run > 0

    with ThreadPoolExecutor(max_workers=max(1, cfg.parallel)) as pool:
        side: dict[Future, tuple[str, Any]] = {}
        if cfg.glossary_per_run:
            side[pool.submit(generate.write_glossary_terms, cfg, llm, [x["term"] for x in store.glossary()],
                             cfg.glossary_per_run)] = ("glossary", None)
        if want_product:
            side[pool.submit(generate.create_product, cfg, llm, existing, products)] = ("product", None)
        stale = [a for a in existing if a.get("version", 1) < generate.ARTICLE_VERSION][: cfg.upgrades_per_run]
        for old in stale:
            topic = {"keyword": old.get("keyword", old["title"]), "niche": old.get("niche", "")}
            side[pool.submit(generate.edit_article, cfg, llm, old, topic)] = ("upgrade", old)

        try:
            topics = generate.plan_topics(cfg, llm, existing, cfg.articles_per_run)
        except LLMError as e:
            topics = []
            report["errors"].append(f"plan: {e}")
        writes = {pool.submit(generate.write_article, cfg, llm, t): t for t in topics}
        for f in as_completed(writes):
            try:
                art = store.save_article(f.result())
                report["articles"].append(art["slug"])
                log.info("published article %s", art["slug"])
            except LLMError as e:
                report["errors"].append(f"article '{writes[f]['title']}': {e}")

        # Promotion kits for this run's articles, plus a couple of older ones that lack a kit.
        by_slug = {a["slug"]: a for a in store.articles()}
        backlog = [s for s, a in by_slug.items() if not store.social(s) and s not in report["articles"]]
        kits = {pool.submit(generate.social_kit, cfg, llm, by_slug[s]): s
                for s in report["articles"] + backlog[:2] if s in by_slug}
        for f in as_completed(kits):
            try:
                store.save_social(kits[f], f.result())
                report.setdefault("social", []).append(kits[f])
            except LLMError as e:
                report["errors"].append(f"social '{kits[f]}': {e}")

        for f in as_completed(side):
            kind, old = side[f]
            try:
                result = f.result()
            except LLMError as e:
                report["errors"].append(f"{kind}{' ' + repr(old['slug']) if old else ''}: {e}")
                continue
            if kind == "glossary":
                report["glossary"] = [store.save_term(x)["slug"] for x in result]
            elif kind == "product":
                slug = _save_product(cfg, store, result, deliverables_dir)
                report["products"].append(slug)
                log.info("created product %s", slug)
            else:
                result.update(slug=old["slug"], published=old["published"])
                store.update_article(result)
                report.setdefault("upgraded", []).append(old["slug"])
                log.info("upgraded article %s", old["slug"])


def run(cfg: Config, llm: JSONModel | None, deliverables_dir: Path | None = None) -> dict[str, Any]:
    store = Store(cfg.content_dir, cfg.data_dir)
    report: dict[str, Any] = {"started": utcnow().isoformat(timespec="seconds"),
                              "articles": [], "products": [], "errors": []}

    if llm is None:
        log.warning("Claude CLI not available or not logged in: skipping generation, rebuilding site only.")
        report["errors"].append("no_credentials")
    else:
        _generate(cfg, llm, store, report, deliverables_dir)

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
