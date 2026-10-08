"""Tell search engines (Bing, Yandex, Seznam, Naver... via IndexNow) about new/updated pages.

Bing's index also feeds ChatGPT search and Copilot, so fast indexing there matters for AI answers.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from .config import Config
from .site import indexnow_key
from .store import Store, utcnow

ENDPOINT = "https://api.indexnow.org/indexnow"


def changed_urls(cfg: Config, store: Store, days: int = 3) -> list[str]:
    since = utcnow() - timedelta(days=days)
    urls = [f"{cfg.base_url}/", f"{cfg.base_url}/guides/", f"{cfg.base_url}/llms.txt"]
    for a in store.articles():
        if datetime.fromisoformat(a.get("updated") or a["published"]) >= since:
            urls.append(f"{cfg.base_url}/{a['slug']}/")
    for p in store.products():
        if datetime.fromisoformat(p["published"]) >= since:
            urls.append(f"{cfg.base_url}/products/{p['slug']}/")
    return urls


def payload(cfg: Config, urls: list[str]) -> dict[str, Any]:
    key = indexnow_key(cfg)
    return {"host": urllib.parse.urlparse(cfg.base_url).netloc, "key": key,
            "keyLocation": f"{cfg.base_url}/{key}.txt", "urlList": urls}


def submit(cfg: Config, store: Store) -> dict[str, Any]:
    urls = changed_urls(cfg, store)
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload(cfg, urls)).encode(),
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return {"status": r.status, "submitted": len(urls)}
    except OSError as e:  # never fail a deploy over a ping
        return {"error": str(e), "submitted": 0}
