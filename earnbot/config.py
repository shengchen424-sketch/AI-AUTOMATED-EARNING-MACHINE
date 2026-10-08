"""Load config.toml into typed objects."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Affiliate:
    name: str
    url: str
    category: str
    blurb: str


@dataclass(frozen=True)
class Niche:
    name: str
    section: str = "Guides"
    care: str = ""          # "", "finance" or "health": stricter rules + on-page disclaimer
    active: bool = True     # False: keeps labelling old articles, but no new ones are written


@dataclass(frozen=True)
class Config:
    site_name: str
    tagline: str
    base_url: str
    language: str
    author: str
    articles_per_run: int
    products_per_run: int
    max_products: int
    model: str
    effort: str
    niches: list[Niche]
    affiliates: list[Affiliate]
    default_price: str
    checkout_links: dict[str, str] = field(default_factory=dict)
    adsense_client: str = ""
    newsletter_action: str = ""
    editor_pass: bool = True
    upgrades_per_run: int = 2
    glossary_per_run: int = 10
    product_interval_hours: int = 20
    business_name: str = ""
    contact_email: str = ""
    refund_days: int = 30
    indexnow: bool = True
    verification: dict[str, str] = field(default_factory=dict)
    root: Path = ROOT

    @property
    def content_dir(self) -> Path:
        return self.root / "content"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def public_dir(self) -> Path:
        return self.root / "public"

    def niche(self, name: str) -> Niche:
        for n in self.niches:
            if n.name.lower() == name.lower():
                return n
        return Niche(name=name)

    def affiliate(self, name: str) -> Affiliate | None:
        for a in self.affiliates:
            if a.name.lower() == name.lower():
                return a
        return None


def load(path: Path | None = None, root: Path | None = None) -> Config:
    path = path or ROOT / "config.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    site, auto = raw["site"], raw["autopilot"]
    checkout = dict(raw.get("checkout", {}))
    default_price = checkout.pop("default_price", "$19")
    return Config(
        site_name=site["name"],
        tagline=site["tagline"],
        base_url=site["base_url"].rstrip("/"),
        language=site.get("language", "en"),
        author=site.get("author", site["name"]),
        articles_per_run=int(auto.get("articles_per_run", 2)),
        products_per_run=int(auto.get("products_per_run", 1)),
        max_products=int(auto.get("max_products", 12)),
        model=auto.get("model", "claude-opus-5-5"),
        effort=auto.get("effort", "high"),
        niches=[Niche(name=n) if isinstance(n, str) else Niche(**n)
                for n in raw.get("niches", auto.get("niches", []))],
        affiliates=[Affiliate(**a) for a in raw.get("affiliates", [])],
        default_price=default_price,
        checkout_links={k: v for k, v in checkout.items() if v},
        adsense_client=raw.get("ads", {}).get("adsense_client", ""),
        newsletter_action=raw.get("newsletter", {}).get("form_action", ""),
        editor_pass=bool(auto.get("editor_pass", True)),
        upgrades_per_run=int(auto.get("upgrades_per_run", 2)),
        glossary_per_run=int(auto.get("glossary_per_run", 10)),
        product_interval_hours=int(auto.get("product_interval_hours", 20)),
        business_name=site.get("business_name", site["name"]),
        contact_email=site.get("contact_email", ""),
        refund_days=int(raw.get("checkout_policy", {}).get("refund_days", 30)),
        indexnow=bool(raw.get("indexnow", {}).get("enabled", True)),
        verification={k: v for k, v in raw.get("verification", {}).items() if v},
        root=root or path.resolve().parent,
    )
