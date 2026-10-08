import json
import shutil
from pathlib import Path

import pytest

from earnbot import config, generate, pipeline
from earnbot.llm import LLMError
from earnbot.revenue import summarize
from earnbot.store import Store, slugify

ROOT = Path(__file__).resolve().parent.parent


class FakeLLM:
    """Returns schema-shaped data so the pipeline runs without network access."""

    def __init__(self, fail_articles=False):
        self.calls = []
        self.fail_articles = fail_articles

    def generate_json(self, system, prompt, schema):
        props = schema["properties"]
        self.calls.append(list(props))
        if "topics" in props:
            return {"topics": [
                {"niche": "n", "keyword": f"kw {i}", "title": f"Topic {i} <b>", "angle": "a",
                 "search_intent": "commercial"} for i in range(6)]}
        if "recommendations" in props:
            if self.fail_articles:
                raise LLMError("boom")
            return {"title": "How to </script><script>alert(1)</script> automate", "meta_description": "desc",
                    "quick_answer": "QUICK ANSWER TEXT", "key_takeaways": ["take 1"], "who_this_is_for": "owners",
                    "steps": [{"name": "Step one", "text": "do it"}],
                    "comparison": {"caption": "Cmp", "headers": ["A", "B"], "rows": [["1", "2"]]},
                    "intro": "intro", "sections": [{"heading": f"H{i}", "paragraphs": ["p"], "bullets": ["b"]} for i in range(3)],
                    "recommendations": [{"product": "Zapier", "best_for": "x", "not_for": "y"},
                                        {"product": "Ghost", "best_for": "x", "not_for": "y"}],
                    "faq": [{"question": "q?", "answer": "a"}], "conclusion": "end"}
        return {"title": "Automation Playbook", "subtitle": "sub", "audience": "owners", "outcomes": ["o"],
                "sales_copy": "copy", "templates": [{"name": "t", "body": "SECRET TEMPLATE"}],
                "chapters": [{"heading": "c1", "summary": "s", "paragraphs": ["SECRET BODY"], "checklist": ["x"]}]}


@pytest.fixture
def cfg(tmp_path):
    shutil.copytree(ROOT / "templates", tmp_path / "templates")
    shutil.copy(ROOT / "config.toml", tmp_path / "config.toml")
    text = (tmp_path / "config.toml").read_text().replace(
        "[checkout]\n", '[checkout]\n"automation-playbook" = "https://buy.stripe.com/test"\n')
    (tmp_path / "config.toml").write_text(text)
    return config.load(tmp_path / "config.toml")


def test_full_run_builds_monetised_site(cfg, tmp_path):
    report = pipeline.run(cfg, FakeLLM(), tmp_path / "deliverables")
    assert len(report["articles"]) == cfg.articles_per_run
    assert report["products"] == ["automation-playbook"]
    pub = cfg.public_dir
    page = (pub / report["articles"][0] / "index.html").read_text()
    assert "<script>alert(1)" not in page            # autoescaped
    assert 'href="https://zapier.com/"' in page and 'rel="sponsored' in page
    assert "Ghost" not in page                        # unknown affiliate dropped
    assert "affiliate links" in page
    prod = (pub / "products" / "automation-playbook" / "index.html").read_text()
    assert "https://buy.stripe.com/test" in prod
    # paid content never reaches the public site or the committed JSON
    assert "SECRET" not in prod
    assert "SECRET" not in (cfg.content_dir / "products" / "automation-playbook.json").read_text()
    assert "SECRET BODY" in (tmp_path / "deliverables" / "automation-playbook.md").read_text()
    for f in ("sitemap.xml", "robots.txt", "feed.xml", "about/index.html", "products/index.html"):
        assert (pub / f).exists()
    assert report["articles"][0] in (pub / "sitemap.xml").read_text()


def test_second_run_does_not_repeat_topics(cfg, tmp_path):
    first = pipeline.run(cfg, FakeLLM(), None)
    second = pipeline.run(cfg, FakeLLM(), None)
    assert not set(first["articles"]) & set(second["articles"])
    assert len(Store(cfg.content_dir, cfg.data_dir).runs()) == 2


def test_no_credentials_only_rebuilds(cfg):
    report = pipeline.run(cfg, None)
    assert report["articles"] == [] and "no_credentials" in report["errors"]
    assert (cfg.public_dir / "index.html").exists()


def test_llm_failures_are_reported_not_fatal(cfg):
    report = pipeline.run(cfg, FakeLLM(fail_articles=True))
    assert report["articles"] == []
    assert any(e.startswith("article") for e in report["errors"])
    assert report["products"]  # other channels keep working


def test_max_products_respected(cfg):
    object.__setattr__(cfg, "max_products", 0)
    assert pipeline.run(cfg, FakeLLM())["products"] == []


def test_product_markdown_contains_everything():
    md = generate.product_markdown(FakeLLM().generate_json("", "", {"properties": {}}))
    assert "SECRET BODY" in md and "SECRET TEMPLATE" in md and "- [ ] x" in md


def test_slugify():
    assert slugify("Hello, World! AI 2026") == "hello-world-ai-2026"
    assert slugify("中文") == "item"


def test_stripe_summary():
    s = summarize([{"currency": "usd", "net": 1800, "amount": 1900, "type": "charge"},
                   {"currency": "usd", "net": -100, "amount": -100, "type": "stripe_fee"}])
    assert s == {"sales": 1, "gross": {"USD": 19.0}, "net": {"USD": 17.0}}


def test_real_config_loads():
    c = config.load()
    assert c.model == "claude-opus-5-5" and c.affiliates and c.niches


def test_editor_pass_and_ai_ready_output(cfg):
    llm = FakeLLM()
    report = pipeline.run(cfg, llm, None)
    article_calls = [c for c in llm.calls if "recommendations" in c]
    assert len(article_calls) == 2 * cfg.articles_per_run          # draft + editor pass
    slug = report["articles"][0]
    pub = cfg.public_dir
    page = (pub / slug / "index.html").read_text()
    assert "QUICK ANSWER TEXT" in page and '"HowTo"' in page and '"FAQPage"' in page and '"BreadcrumbList"' in page
    assert 'og:image' in page and f"assets/og/{slug}.png" in page
    assert (pub / "assets" / "og" / f"{slug}.png").stat().st_size > 1000
    md = (pub / slug / "index.md").read_text()
    assert "## Quick answer" in md and "| A | B |" in md
    robots = (pub / "robots.txt").read_text()
    assert "User-agent: GPTBot" in robots and "User-agent: ClaudeBot" in robots and "Sitemap:" in robots
    assert slug in (pub / "llms.txt").read_text() and "QUICK ANSWER TEXT" in (pub / "llms-full.txt").read_text()
    for legal in ("terms", "privacy", "refund-policy", "contact"):
        assert (pub / legal / "index.html").exists()
    prod = (pub / "products" / "automation-playbook" / "index.html").read_text()
    assert '"Product"' in prod and '"price": "19"' in prod


def test_old_articles_are_upgraded_in_place(cfg):
    store = Store(cfg.content_dir, cfg.data_dir)
    old = store.save_article({"title": "Old guide", "meta_description": "d", "intro": "i", "sections": [],
                              "recommendations": [], "faq": [], "conclusion": "c", "keyword": "old kw", "niche": "n"})
    report = pipeline.run(cfg, FakeLLM(), None)
    assert old["slug"] in report["upgraded"]
    new = json.loads((cfg.content_dir / "articles" / f"{old['slug']}.json").read_text())
    assert new["version"] == generate.ARTICLE_VERSION and new["published"] == old["published"] and new["updated"]
    assert new["quick_answer"] == "QUICK ANSWER TEXT"


def test_indexnow_payload(cfg):
    from earnbot import indexnow, site as site_mod
    pipeline.run(cfg, FakeLLM(), None)
    store = Store(cfg.content_dir, cfg.data_dir)
    body = indexnow.payload(cfg, indexnow.changed_urls(cfg, store))
    assert body["keyLocation"].endswith(".txt") and len(body["urlList"]) >= 3
    assert (cfg.public_dir / f"{site_mod.indexnow_key(cfg)}.txt").read_text() == body["key"]
