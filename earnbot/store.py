"""File-based storage: every article/product is one JSON file committed to git."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def slugify(text: str, max_len: int = 70) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "item"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self, content_dir: Path, data_dir: Path):
        self.articles_dir = content_dir / "articles"
        self.products_dir = content_dir / "products"
        self.data_dir = data_dir
        for d in (self.articles_dir, self.products_dir, self.data_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ---- generic -------------------------------------------------------
    @staticmethod
    def _load_dir(d: Path) -> list[dict[str, Any]]:
        items = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]
        return sorted(items, key=lambda x: x.get("published", ""), reverse=True)

    @staticmethod
    def _unique_slug(d: Path, slug: str) -> str:
        candidate, n = slug, 2
        while (d / f"{candidate}.json").exists():
            candidate, n = f"{slug}-{n}", n + 1
        return candidate

    def _save(self, d: Path, item: dict[str, Any]) -> dict[str, Any]:
        item["slug"] = self._unique_slug(d, slugify(item.get("slug") or item["title"]))
        item.setdefault("published", utcnow().isoformat(timespec="seconds"))
        (d / f"{item['slug']}.json").write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return item

    # ---- articles / products ------------------------------------------
    def articles(self) -> list[dict[str, Any]]:
        return self._load_dir(self.articles_dir)

    def products(self) -> list[dict[str, Any]]:
        return self._load_dir(self.products_dir)

    def save_article(self, article: dict[str, Any]) -> dict[str, Any]:
        return self._save(self.articles_dir, article)

    def save_product(self, product: dict[str, Any]) -> dict[str, Any]:
        return self._save(self.products_dir, product)

    # ---- run log / revenue --------------------------------------------
    def log_run(self, entry: dict[str, Any]) -> None:
        with (self.data_dir / "runs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def runs(self) -> list[dict[str, Any]]:
        p = self.data_dir / "runs.jsonl"
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    def save_revenue(self, report: dict[str, Any]) -> None:
        (self.data_dir / "revenue.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def revenue(self) -> dict[str, Any] | None:
        p = self.data_dir / "revenue.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
