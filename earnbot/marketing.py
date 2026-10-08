"""Automatic promotion: publish new articles (and playbooks) to the owner's social channels.

Every channel is opt-in: it only runs when its credentials are present as environment
variables (GitHub Secrets). Posts are de-duplicated via data/marketing/posted.json and
capped per channel per day so accounts never look like spam.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .store import Store, utcnow

log = logging.getLogger("earnbot")

DAILY_CAP = 8          # posts per channel per rolling 24h
PER_RUN_CAP = 4        # posts per channel per run


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _request(url: str, data: Any = None, headers: dict[str, str] | None = None, form: bool = False) -> dict[str, Any]:
    body = None
    hdrs = dict(headers or {})
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            body = json.dumps(data).encode()
            hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Channels: each takes a Post and returns the remote id/url.
# ---------------------------------------------------------------------------
class Post(dict):
    """keys: kind, slug, title, url, hook, long, image, tags, section"""


def telegram(p: Post) -> str:
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    text = f"{p['title']}\n\n{_cut(p['long'], 900)}\n\n{p['url']}"
    r = _request(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat, "text": text})
    return str(r.get("result", {}).get("message_id", ""))


def bluesky(p: Post) -> str:
    base = os.environ.get("BLUESKY_SERVICE", "https://bsky.social")
    s = _request(f"{base}/xrpc/com.atproto.server.createSession",
                 {"identifier": os.environ["BLUESKY_HANDLE"], "password": os.environ["BLUESKY_APP_PASSWORD"]})
    record = {
        "$type": "app.bsky.feed.post",
        "text": _cut(p["hook"], 290),
        "createdAt": utcnow().isoformat().replace("+00:00", "Z"),
        "langs": ["en"],
        "embed": {"$type": "app.bsky.embed.external",
                  "external": {"uri": p["url"], "title": _cut(p["title"], 200), "description": _cut(p["long"], 280)}},
    }
    r = _request(f"{base}/xrpc/com.atproto.repo.createRecord",
                 {"repo": s["did"], "collection": "app.bsky.feed.post", "record": record},
                 {"Authorization": f"Bearer {s['accessJwt']}"})
    return r.get("uri", "")


def mastodon(p: Post) -> str:
    instance = os.environ["MASTODON_INSTANCE"].rstrip("/")
    tags = " ".join("#" + t for t in p["tags"][:4])
    status = f"{_cut(p['hook'], 380)}\n\n{p['url']}\n\n{tags}".strip()
    r = _request(f"{instance}/api/v1/statuses", {"status": status, "visibility": "public"},
                 {"Authorization": f"Bearer {os.environ['MASTODON_TOKEN']}",
                  "Idempotency-Key": hashlib.sha256(p["url"].encode()).hexdigest()})
    return r.get("url", "")


def facebook(p: Post) -> str:
    page = os.environ["FACEBOOK_PAGE_ID"]
    r = _request(f"https://graph.facebook.com/v21.0/{page}/feed",
                 {"message": _cut(p["long"], 1500), "link": p["url"], "access_token": os.environ["FACEBOOK_PAGE_TOKEN"]},
                 form=True)
    return r.get("id", "")


def pinterest(p: Post) -> str:
    if not p.get("image"):
        return "skipped:no-image"
    r = _request("https://api.pinterest.com/v5/pins", {
        "board_id": os.environ["PINTEREST_BOARD_ID"], "title": _cut(p["title"], 100),
        "description": _cut(p["long"], 480), "link": p["url"], "alt_text": _cut(p["title"], 400),
        "media_source": {"source_type": "image_url", "url": p["image"]},
    }, {"Authorization": f"Bearer {os.environ['PINTEREST_TOKEN']}"})
    return r.get("id", "")


def _oauth1_header(method: str, url: str, keys: dict[str, str]) -> str:
    oauth = {"oauth_consumer_key": keys["ck"], "oauth_nonce": secrets.token_hex(16),
             "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(int(time.time())),
             "oauth_token": keys["at"], "oauth_version": "1.0"}
    q = lambda s: urllib.parse.quote(str(s), safe="")
    params = "&".join(f"{q(k)}={q(v)}" for k, v in sorted(oauth.items()))
    base = "&".join([method, q(url), q(params)])
    key = f"{q(keys['cs'])}&{q(keys['as'])}"
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{q(k)}="{q(v)}"' for k, v in sorted(oauth.items()))


def x_twitter(p: Post) -> str:
    url = "https://api.x.com/2/tweets"
    keys = {"ck": os.environ["X_API_KEY"], "cs": os.environ["X_API_SECRET"],
            "at": os.environ["X_ACCESS_TOKEN"], "as": os.environ["X_ACCESS_SECRET"]}
    text = f"{_cut(p['hook'], 250)}\n\n{p['url']}"   # links count as 23 chars on X
    r = _request(url, {"text": text}, {"Authorization": _oauth1_header("POST", url, keys)})
    return r.get("data", {}).get("id", "")


def devto(p: Post) -> str:
    # Developer audience: only AI & Tech guides, published with a canonical link back to us.
    if p.get("section") != "AI & Tech" or p["kind"] != "article" or not p.get("markdown"):
        return "skipped:off-topic"
    r = _request("https://dev.to/api/articles", {"article": {
        "title": _cut(p["title"], 120), "body_markdown": p["markdown"], "published": True,
        "canonical_url": p["url"], "description": _cut(p["long"], 150),
        "tags": [t.lower().replace(" ", "")[:20] for t in p["tags"]][:4],
    }}, {"api-key": os.environ["DEVTO_API_KEY"]})
    return r.get("url", "")


CHANNELS: dict[str, tuple[tuple[str, ...], Callable[[Post], str]]] = {
    "telegram": (("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"), telegram),
    "bluesky": (("BLUESKY_HANDLE", "BLUESKY_APP_PASSWORD"), bluesky),
    "mastodon": (("MASTODON_INSTANCE", "MASTODON_TOKEN"), mastodon),
    "facebook": (("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_TOKEN"), facebook),
    "pinterest": (("PINTEREST_TOKEN", "PINTEREST_BOARD_ID"), pinterest),
    "x": (("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"), x_twitter),
    "devto": (("DEVTO_API_KEY",), devto),
}


def enabled_channels() -> list[str]:
    return [name for name, (env, _) in CHANNELS.items() if all(os.environ.get(e) for e in env)]


# ---------------------------------------------------------------------------
# Queue: what to post next
# ---------------------------------------------------------------------------
def _utm(url: str, source: str, campaign: str) -> str:
    return f"{url}?utm_source={source}&utm_medium=social&utm_campaign={campaign[:40]}"


def build_queue(cfg: Config, store: Store) -> list[Post]:
    from .site import article_markdown  # local import: site imports heavy deps
    posts: list[Post] = []
    # Paid playbooks with a checkout link go first (they make money directly).
    for p in store.products():
        if p["slug"] in cfg.checkout_links:
            posts.append(Post(kind="product", slug=f"product:{p['slug']}", title=p["title"],
                              url=f"{cfg.base_url}/products/{p['slug']}/", hook=f"{p['title']} — {p['subtitle']}",
                              long=p["sales_copy"], image=f"{cfg.base_url}/assets/og/site.png",
                              tags=["personalfinance", "money", "productivity"], section=p.get("section", "")))
    for a in store.articles():  # newest first
        kit = store.social(a["slug"]) or {}
        thread = kit.get("x_thread") or []
        hook = (thread[0] if thread else a.get("quick_answer") or a["meta_description"]).replace("{URL}", "").strip()
        posts.append(Post(kind="article", slug=a["slug"], title=a["title"], url=f"{cfg.base_url}/{a['slug']}/",
                          hook=hook, long=(kit.get("facebook_post") or a.get("quick_answer") or a["meta_description"]).replace("{URL}", "").strip(),
                          image=f"{cfg.base_url}/assets/pins/{a['slug']}.png",
                          tags=[h.lstrip("#").replace(" ", "") for h in kit.get("hashtags", [])] or ["money"],
                          section=cfg.niche(a.get("niche", "")).section, markdown=article_markdown(cfg, a)))
    return posts


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _load_log(path: Path) -> dict[str, dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def promote(cfg: Config, store: Store, channels: list[str] | None = None) -> dict[str, Any]:
    channels = channels if channels is not None else enabled_channels()
    log_path = store.data_dir / "marketing" / "posted.json"
    posted = _load_log(log_path)   # {channel: {slug: "timestamp|remote-id"}}
    now = utcnow()
    result: dict[str, Any] = {"channels": channels, "posted": {}, "errors": []}
    queue = build_queue(cfg, store)
    for ch in channels:
        _, fn = CHANNELS[ch]
        done = posted.setdefault(ch, {})
        recent = sum(1 for v in done.values() if now - datetime.fromisoformat(v.split("|")[0]) < timedelta(hours=24))
        budget = min(PER_RUN_CAP, DAILY_CAP - recent)
        for post in queue:
            if budget <= 0:
                break
            if post["slug"] in done:
                last = datetime.fromisoformat(done[post["slug"]].split("|")[0])
                # Articles are posted once; paid playbooks are re-promoted weekly.
                if post["kind"] != "product" or now - last < timedelta(days=7):
                    continue
            post = Post(post, url=_utm(post["url"], ch, post["slug"].replace("product:", "")))
            try:
                remote = fn(post)
            except Exception as e:  # one bad channel/post must never stop the others
                result["errors"].append(f"{ch} '{post['slug']}': {e}")
                break
            done[post["slug"]] = f"{now.isoformat(timespec='seconds')}|{remote}"
            if not str(remote).startswith("skipped"):
                result["posted"].setdefault(ch, []).append(post["slug"])
                budget -= 1
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(posted, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
