"""Turn a playbook into a polished, print-ready HTML + PDF deliverable (headless Chrome)."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

_CHROMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
            "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"]

_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{{ p.title }}</title>
<style>
@page{size:A4;margin:22mm 20mm}@page :first{margin:0}
html,body{margin:0}body{-webkit-print-color-adjust:exact;print-color-adjust:exact;font:11pt/1.6 "Inter","DejaVu Sans",Arial,sans-serif;color:#1b1f2a}
h1,h2,h3{line-height:1.25;color:#141824}
.cover{height:296mm;display:flex;flex-direction:column;justify-content:center;page-break-after:always;
  background:linear-gradient(135deg,#4f46e5,#7c3aed 45%,#06b6d4);color:#fff;margin:0;padding:0 26mm;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}
.cover h1{color:#fff;font-size:34pt;margin:0 0 10pt}.cover p{font-size:14pt;opacity:.92}
.cover .brand{margin-top:40pt;font-weight:700;letter-spacing:.06em;text-transform:uppercase;font-size:10pt}
.toc{page-break-after:always}.toc li{margin:5pt 0}
h2{font-size:18pt;margin-top:0;padding-top:4pt;border-bottom:2pt solid #4f46e5;padding-bottom:4pt}
.chapter{page-break-before:always}
.box{background:#f3f5fb;border-left:4pt solid #4f46e5;padding:10pt 14pt;margin:12pt 0;border-radius:4pt}
.check li{list-style:none;margin:4pt 0}.check li:before{content:"\\2610  ";color:#4f46e5}
pre{white-space:pre-wrap;background:#f6f7fb;border:1px solid #e3e6ef;border-radius:6pt;padding:10pt;font:9.5pt/1.5 "DejaVu Sans Mono",monospace;page-break-inside:avoid}
.muted{color:#5b6475}
</style></head><body>
<section class="cover"><h1>{{ p.title }}</h1><p>{{ p.subtitle }}</p><div class="brand">{{ brand }}</div></section>
<section class="toc"><h2>Contents</h2>
<div class="box"><b>Who this is for:</b> {{ p.audience }}</div>
<h3>What you'll achieve</h3><ul>{% for o in p.outcomes %}<li>{{ o }}</li>{% endfor %}</ul>
<h3>Chapters</h3><ol>{% for c in p.chapters %}<li>{{ c.heading|clean }}</li>{% endfor %}{% if p.templates %}<li>Templates</li>{% endif %}</ol>
</section>
{% for c in p.chapters %}<section class="chapter"><h2>{{ loop.index }}. {{ c.heading|clean }}</h2>
<p class="muted"><i>{{ c.summary }}</i></p>
{% for para in c.paragraphs %}<p>{{ para }}</p>{% endfor %}
{% if c.checklist %}<div class="box"><b>Checklist</b><ul class="check">{% for x in c.checklist %}<li>{{ x }}</li>{% endfor %}</ul></div>{% endif %}
</section>{% endfor %}
{% if p.templates %}<section class="chapter"><h2>Templates</h2>
{% for t in p.templates %}<h3>{{ loop.index }}. {{ t.name|clean }}</h3><pre>{{ t.body }}</pre>{% endfor %}</section>{% endif %}
<p class="muted" style="margin-top:24pt">© {{ brand }}. Licensed for use in your own business; please don't redistribute.</p>
</body></html>"""


def product_html(product: dict[str, Any], brand: str) -> str:
    env = Environment(autoescape=select_autoescape(default=True))
    # Models often number headings themselves ("Chapter 3: ...", "8. ..."); we number them ourselves.
    env.filters["clean"] = lambda s: re.sub(r"^\s*(chapter\s+\d+\s*[:.\-–]\s*|\d+[.)]\s*)", "", s, flags=re.I)
    return env.from_string(_TEMPLATE).render(p=product, brand=brand)


def find_chrome() -> str | None:
    for c in _CHROMES:
        if path := shutil.which(c) or (c if Path(c).exists() else None):
            return path
    return None


def html_to_pdf(html: str, out: Path) -> bool:
    chrome = find_chrome()
    if not chrome:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.html"
        src.write_text(html, encoding="utf-8")
        try:
            subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={out}", src.as_uri()],
                           check=True, capture_output=True, timeout=120)
        except (subprocess.SubprocessError, OSError):
            return False
    return out.exists() and out.stat().st_size > 0
