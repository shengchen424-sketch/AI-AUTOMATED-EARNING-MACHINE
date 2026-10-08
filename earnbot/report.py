"""Human-readable (Chinese) report of what each autopilot run produced."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .config import Config
from .store import Store

SECTION_ZH = {
    "Investing": "投资（股票/ETF/加密）",
    "Banking & Money": "银行与理财",
    "Accounting & Business": "会计与商业财务",
    "Self-Development": "自我提升",
    "AI & Tech": "AI 与科技",
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
           f"**新文章 {len(new)} 篇 · 升级旧文章 {len(upgraded)} 篇 · 新手册 {len(made)} 本 · 新术语 {len(run.get('glossary', []))} 个**"
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
        out += ["## 🆕 新文章", "", *article_rows(new), "", "### 📝 内容大纲", ""]
        for s in new:
            a = by_slug.get(s)
            if not a:
                continue
            outline = [x["heading"] for x in a.get("sections", [])]
            if a.get("steps"):
                outline.insert(0, f"Step-by-step（{len(a['steps'])} 步）")
            out += [f"**{a['title']}**（{_zh(cfg.niche(a.get('niche', '')).section)}）", "",
                    *[f"{i}. {h}" for i, h in enumerate(outline, 1)],
                    f"{len(outline) + 1}. FAQ（{len(a.get('faq', []))} 题）" if a.get("faq") else "", ""]
    if upgraded:
        out += ["## ♻️ 升级到新格式的旧文章", "", *article_rows(upgraded), ""]
    if made:
        out += ["## 📘 新付费手册", ""]
        for s in made:
            p = products.get(s, {})
            out += [f"- **{p.get('title', s)}**（{_zh(p.get('section', ''))}）— {p.get('subtitle', '')}",
                    f"  - 销售页：{cfg.base_url}/products/{s}/",
                    *[f"  - 第 {i} 章：{c['heading']}" for i, c in enumerate(p.get("chapters", []), 1)]]
        out += ["", "**需要你操作（每本新手册一次）：**",
                f"1. 下载 PDF：{run_url or '本次运行页面'} → 最下方 Artifacts → `deliverables-…`",
                "2. 上传到 Google Drive，设为「知道链接的任何人可查看」",
                f"3. Stripe → Payment Links → 新建，价格 {cfg.default_price}，After payment 的自定义消息里贴 Drive 链接",
                "4. 把 `buy.stripe.com/...` 链接发给 Claude，填到网站上（没填之前页面显示 Launching soon）", ""]

    kits = [(s, store.social(s)) for s in run.get("social", [])]
    kits = [(s, k) for s, k in kits if k]
    if kits:
        out += ["## 📣 社交推广素材（复制即可发布）", "",
                "_链接已带追踪参数（utm），以后能看出哪个平台带来访客。发 Reddit / Facebook 群组前先看该群的推广规则。_", ""]
        for s, k in kits:
            title = by_slug.get(s, {}).get("title", s)
            link = lambda src: f"{cfg.base_url}/{s}/?utm_source={src}&utm_medium=social&utm_campaign={s[:40]}"
            fill = lambda text, src: text.replace("{URL}", link(src))
            tags = " ".join("#" + h.lstrip("#").replace(" ", "") for h in k.get("hashtags", []))
            out += [f"<details><summary><b>{title}</b></summary>", "",
                    "**X (Twitter) 串文**", "", *[f"{i}. {fill(p, 'x')}" for i, p in enumerate(k["x_thread"], 1)], "",
                    "**LinkedIn**", "", fill(k["linkedin_post"], "linkedin"), "", tags, "",
                    "**Facebook**", "", fill(k["facebook_post"], "facebook"), "",
                    f"**Reddit**（建议版块：{', '.join(k['suggested_subreddits'])}）", "",
                    f"标题：{k['reddit_title']}", "", fill(k["reddit_post"], "reddit"), "",
                    "**Pinterest**", "", f"标题：{k['pinterest_title']}", "", k["pinterest_description"], "",
                    f"图片：{cfg.base_url}/assets/pins/{s}.png", "", f"链接：{link('pinterest')}", "",
                    "</details>", ""]

    gl = run.get("glossary", [])
    if gl:
        out += [f"## 📖 新增术语 {len(gl)} 个", "", ", ".join(f"[{g}]({cfg.base_url}/glossary/{g}/)" for g in gl), ""]

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
