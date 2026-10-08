import json

import pytest

from earnbot import marketing, pipeline
from earnbot.store import Store
from tests.test_pipeline import FakeLLM, cfg  # noqa: F401  (fixture)

ALL_ENV = {
    "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "@c", "BLUESKY_HANDLE": "me.bsky.social",
    "BLUESKY_APP_PASSWORD": "p", "MASTODON_INSTANCE": "https://mastodon.social", "MASTODON_TOKEN": "m",
    "FACEBOOK_PAGE_ID": "1", "FACEBOOK_PAGE_TOKEN": "f", "PINTEREST_TOKEN": "pt", "PINTEREST_BOARD_ID": "b",
    "X_API_KEY": "a", "X_API_SECRET": "b", "X_ACCESS_TOKEN": "c", "X_ACCESS_SECRET": "d", "DEVTO_API_KEY": "k",
}


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(url, data=None, headers=None, form=False):
        seen.append({"url": url, "data": data, "headers": headers or {}})
        if "createSession" in url:
            return {"did": "did:plc:x", "accessJwt": "jwt"}
        if "/broken/" in url:
            raise OSError("boom")
        return {"id": "1", "uri": "at://x", "url": "https://x", "result": {"message_id": 5}, "data": {"id": "9"}}

    monkeypatch.setattr(marketing, "_request", fake)
    for k, v in ALL_ENV.items():
        monkeypatch.setenv(k, v)
    return seen


def test_all_channels_enabled_and_capped(cfg, calls):
    for _ in range(3):
        pipeline.run(cfg, FakeLLM(), None)               # 6 articles
    store = Store(cfg.content_dir, cfg.data_dir)
    assert set(marketing.enabled_channels()) == set(marketing.CHANNELS)
    result = marketing.promote(cfg, store)
    for ch in ("telegram", "bluesky", "mastodon", "facebook", "pinterest", "x"):
        assert len(result["posted"][ch]) == marketing.PER_RUN_CAP, ch
    assert "devto" not in result["posted"]                # finance/other sections are skipped on Dev.to
    tg = next(c for c in calls if "api.telegram.org" in c["url"])
    assert "utm_source=telegram" in tg["data"]["text"]
    x = next(c for c in calls if "api.x.com" in c["url"])
    assert x["headers"]["Authorization"].startswith("OAuth ") and 'oauth_signature="' in x["headers"]["Authorization"]
    bs = next(c for c in calls if "createRecord" in c["url"])
    assert bs["data"]["record"]["embed"]["external"]["uri"].startswith(cfg.base_url)

    # Second run continues with the remaining posts and never repeats one.
    second = marketing.promote(cfg, store)
    first_tg, second_tg = set(result["posted"]["telegram"]), set(second["posted"].get("telegram", []))
    assert not first_tg & second_tg
    log = json.loads((cfg.data_dir / "marketing" / "posted.json").read_text())
    assert len(log["telegram"]) == len(first_tg | second_tg)


def test_daily_cap(cfg, calls, monkeypatch):
    monkeypatch.setattr(marketing, "DAILY_CAP", 5)      # fake model yields 7 postable items
    for _ in range(3):
        pipeline.run(cfg, FakeLLM(), None)
    store = Store(cfg.content_dir, cfg.data_dir)
    total = sum(len(marketing.promote(cfg, store, ["telegram"])["posted"].get("telegram", [])) for _ in range(4))
    assert total == marketing.DAILY_CAP


def test_failing_channel_does_not_stop_others(cfg, calls, monkeypatch):
    pipeline.run(cfg, FakeLLM(), None)
    monkeypatch.setenv("MASTODON_INSTANCE", "https://broken/")
    result = marketing.promote(cfg, Store(cfg.content_dir, cfg.data_dir), ["mastodon", "telegram"])
    assert result["errors"] and result["posted"]["telegram"]


def test_no_secrets_means_no_channels(monkeypatch):
    for k in ALL_ENV:
        monkeypatch.delenv(k, raising=False)
    assert marketing.enabled_channels() == []
