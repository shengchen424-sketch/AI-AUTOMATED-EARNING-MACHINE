"""Human-readable (Chinese) report of what each autopilot run produced."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .config import Config
from .store import Store

SECTION_ZH = {
    "AI & Work": "AI 与工作",
    "Money & Finance": "金融理财",
    "Baby & Parenting": "婴儿与育儿",
    "Kids & Education": "儿童与教育",
}


def _zh(section: str) -> str:
    return SECTION_ZH.get(section, section or "其他")


def _short(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def render(cfg: Config, store: Store, run: dict[str, Any], run_url: str = "") -> str:
    by_slug = {a["slug"]: a for a in store.articles()}
    products = {p["slug"]: p for p in store.products()}
    date = run.get("started", "")[:10]
    new, upgraded, made = run.get("articles", []), run.get("upgraded", []), run.get("products", [])

    out = [f"# 📊 自动运行报告 {date}", "",
           f"**新文章 {len(new)} 篇 · 升级旧文章 {len(upgraded)} 篇 · 新手册 {len(made)} 本**"
           + (f" · ⚠️ 问题 {len(run.get('errors', []))} 个" if run.get("errors") else ""), "",
           f"网站：{cfg.base_url}/", ""]

    def article_rows(slugs: list[str]) -> list[str]:
        rows = ["| 类别 | 标题 | 一句话摘要 |", "|---|---|---|"]
        for s in slugs:
            a = by_slug.get(s)
            if not a:
                continue
            summary = _short(a.get("quick_answer") or a.get("meta_description", "")).replace("|", "/")
            rows.append(f"| {_zh(cfg.niche(a.get('niche', '')).section)} | [{a['title']}]({cfg.base_url}/{s}/) | {summary} |")
        return rows

    if new:
        out += ["## 🆕 新文章", "", *article_rows(new), ""]
    if upgraded:
        out += ["## ♻️ 升级到新格式的旧文章", "", *article_rows(upgraded), ""]
    if made:
        out += ["## 📘 新付费手册", ""]
        for s in made:
            p = products.get(s, {})
            out += [f"- **{p.get('title', s)}**（{_zh(p.get('section', ''))}）— {p.get('subtitle', '')}",
                    f"  - 销售页：{cfg.base_url}/products/{s}/"]
        out += ["", "**需要你操作（每本新手册一次）：**",
                f"1. 下载 PDF：{run_url or '本次运行页面'} → 最下方 Artifacts → `deliverables-…`",
                "2. 上传到 Google Drive，设为「知道链接的任何人可查看」",
                f"3. Stripe → Payment Links → 新建，价格 {cfg.default_price}，After payment 的自定义消息里贴 Drive 链接",
                "4. 把 `buy.stripe.com/...` 链接发给 Claude，填到网站上（没填之前页面显示 Launching soon）", ""]

    counts = Counter(_zh(cfg.niche(a.get("niche", "")).section) for a in by_slug.values())
    out += ["## 📚 全站内容统计", "", "| 类别 | 文章数 |", "|---|---|",
            *[f"| {k} | {v} |" for k, v in counts.most_common()],
            f"| **合计** | **{len(by_slug)}** |", "", f"付费手册：{len(products)} 本", ""]

    if run.get("errors"):
        out += ["## ⚠️ 问题", "", *[f"- `{_short(e, 300)}`" for e in run["errors"]], "",
                "_单次失败不影响网站，下次运行会自动重试。连续多天失败请告诉 Claude。_", ""]
    if not new and not made and "no_credentials" in run.get("errors", []):
        out += ["> 本次没有生成内容：缺少 `CLAUDE_CODE_OAUTH_TOKEN`（或这是只重建网站的 push 运行）。", ""]
    return "\n".join(out)
