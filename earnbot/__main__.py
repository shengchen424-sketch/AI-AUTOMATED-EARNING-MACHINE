"""CLI:  python -m earnbot run | build | status"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import config, indexnow, pipeline, report, site
from .llm import ClaudeCodeJSON, has_credentials
from .store import Store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="earnbot", description="AI Earning Machine autopilot")
    ap.add_argument("command", choices=["run", "build", "status", "indexnow", "burst"])
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--deliverables", type=Path, default=Path("deliverables"),
                    help="where full paid product files are written (kept out of the public site)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = config.load(args.config)

    if args.command == "run":
        llm = ClaudeCodeJSON(cfg.model, cfg.effort) if has_credentials() else None
        result = pipeline.run(cfg, llm, args.deliverables)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        text = report.render(cfg, Store(cfg.content_dir, cfg.data_dir), result, os.environ.get("RUN_URL", ""))
        Path("report.md").write_text(text, encoding="utf-8")
        reports = cfg.data_dir / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / f"{result['started'][:16].replace(':', '')}.md").write_text(text, encoding="utf-8")
        # Fail the job only when generation was attempted and produced nothing.
        return 1 if llm and result["errors"] and not result["articles"] and not result["products"] else 0

    store = Store(cfg.content_dir, cfg.data_dir)
    if args.command == "build":
        print(json.dumps(site.build(cfg, store)))
        return 0
    if args.command == "burst":
        # Exit 0 = keep chaining runs (still inside the burst window), 1 = stop.
        from datetime import datetime, timezone
        if not cfg.burst_until:
            return 1
        until = datetime.fromisoformat(cfg.burst_until.replace("Z", "+00:00"))
        active = datetime.now(timezone.utc) < until
        print(f"burst {'active' if active else 'over'} (until {cfg.burst_until})")
        return 0 if active else 1
    if args.command == "indexnow":
        print(json.dumps(indexnow.submit(cfg, store) if cfg.indexnow else {"skipped": "disabled in config"}))
        return 0

    runs = store.runs()
    print(json.dumps({
        "articles": len(store.articles()),
        "products": len(store.products()),
        "runs": len(runs),
        "last_run": runs[-1] if runs else None,
        "revenue": store.revenue(),
        "checkout_links": len(cfg.checkout_links),
        "affiliates": len(cfg.affiliates),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
