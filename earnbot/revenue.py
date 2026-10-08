"""Pull real sales numbers from Stripe (read-only) when STRIPE_API_KEY is set."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import timedelta
from typing import Any

from .store import utcnow

STRIPE_API = "https://api.stripe.com/v1/balance_transactions"


def _fetch(key: str, since: int) -> list[dict[str, Any]]:
    txns: list[dict[str, Any]] = []
    params: dict[str, Any] = {"limit": 100, "created[gte]": since}
    while True:
        req = urllib.request.Request(f"{STRIPE_API}?{urllib.parse.urlencode(params)}",
                                     headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = json.load(r)
        txns += page["data"]
        if not page.get("has_more") or not page["data"]:
            return txns
        params["starting_after"] = page["data"][-1]["id"]


def summarize(txns: list[dict[str, Any]]) -> dict[str, Any]:
    net: dict[str, int] = defaultdict(int)
    gross: dict[str, int] = defaultdict(int)
    sales = 0
    for t in txns:
        cur = t["currency"].upper()
        net[cur] += t["net"]
        if t["type"] in ("charge", "payment"):
            gross[cur] += t["amount"]
            sales += 1
    return {
        "sales": sales,
        "gross": {c: v / 100 for c, v in gross.items()},
        "net": {c: v / 100 for c, v in net.items()},
    }


def stripe_report(days: int = 30, key: str | None = None) -> dict[str, Any] | None:
    key = key or os.environ.get("STRIPE_API_KEY")
    if not key:
        return None
    since = int((utcnow() - timedelta(days=days)).timestamp())
    report = summarize(_fetch(key, since))
    report.update(source="stripe", window_days=days, updated=utcnow().isoformat(timespec="seconds"))
    return report
