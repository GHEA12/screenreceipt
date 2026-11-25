"""Deterministic fact collection for ScreenReceipt.

The model never collects facts. Every check in this module is a pure function
over the listing text/fields: same input, same facts, no network, no model.
Each check returns a Finding with the exact evidence string it matched, so a
human (or the verify step) can audit the judge's verdict against the facts.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class Listing:
    title: str
    body: str
    price: float | None = None
    reference_price: float | None = None
    seller: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()


@dataclass
class Finding:
    check: str
    status: str  # "pass" | "warn" | "fail"
    weight: int  # risk points contributed when status != pass
    evidence: str
    detail: str = ""


# --- check patterns -------------------------------------------------------
# Each entry: (phrase or regex, weight). Matching is case-insensitive on the
# listing text. These are deliberately conservative, well-known scam signals.

RED_FLAG_PHRASES: list[tuple[str, int]] = [
    (r"gift cards?", 30),
    (r"crypto(currency)? only", 25),
    (r"wire transfer", 20),
    (r"western union|moneygram", 25),
    (r"send (a )?deposit (first|before)", 25),
    (r"pay(ment)? in advance", 20),
    (r"no (need to )?(meet|viewing|inspection)", 15),
    (r"i am (currently )?(abroad|overseas|out of the country)", 15),
    (r"shipping agent", 15),
    (r"double your (money|investment)", 35),
    (r"guaranteed (profit|returns?|income)", 30),
    (r"risk[- ]free investment", 25),
]

URGENCY_PHRASES: list[tuple[str, int]] = [
    (r"act now", 8),
    (r"only \d+ (spots?|left|available)", 8),
    (r"first come", 6),
    (r"today only", 8),
    (r"urgent(ly)? (need|selling)", 8),
    (r"price (goes|going) up", 6),
]

OFF_PLATFORM_PATTERNS: list[tuple[str, int]] = [
    (r"whatsapp", 12),
    (r"telegram", 12),
    (r"\btext me at\b", 10),
    (r"contact me (outside|off) (the )?(app|platform|site)", 20),
    (r"\b\d{2,4}[- ]\d{3,4}[- ]\d{3,4}\b", 8),  # phone-number-like
]


def _scan(text: str, patterns: list[tuple[str, int]]) -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    for pattern, weight in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            hits.append((m.group(0), weight))
    return hits


def check_red_flags(listing: Listing) -> Finding:
    hits = _scan(listing.text, RED_FLAG_PHRASES)
    if not hits:
        return Finding("red_flag_phrases", "pass", 0, "no known scam phrases matched")
    weight = sum(w for _, w in hits)
    evidence = "; ".join(f'"{h}"' for h, _ in hits)
    return Finding(
        "red_flag_phrases",
        "fail" if weight >= 25 else "warn",
        weight,
        f"matched: {evidence}",
    )


def check_off_platform_contact(listing: Listing) -> Finding:
    hits = _scan(listing.text, OFF_PLATFORM_PATTERNS)
    if not hits:
        return Finding("off_platform_contact", "pass", 0, "no off-platform contact lure found")
    weight = sum(w for _, w in hits)
    evidence = "; ".join(f'"{h}"' for h, _ in hits)
    return Finding(
        "off_platform_contact",
        "fail" if weight >= 20 else "warn",
        weight,
        f"matched: {evidence}",
    )


def check_urgency(listing: Listing) -> Finding:
    hits = _scan(listing.text, URGENCY_PHRASES)
    if not hits:
        return Finding("urgency_language", "pass", 0, "no urgency pressure language found")
    weight = sum(w for _, w in hits)
    evidence = "; ".join(f'"{h}"' for h, _ in hits)
    return Finding("urgency_language", "warn", weight, f"matched: {evidence}")


def check_price_anomaly(listing: Listing) -> Finding:
    if listing.price is None or listing.reference_price is None:
        return Finding(
            "price_anomaly",
            "pass",
            0,
            "no price/reference pair supplied; check skipped",
            detail="skipped",
        )
    if listing.reference_price <= 0:
        return Finding("price_anomaly", "pass", 0, "reference price not usable", detail="skipped")
    ratio = listing.price / listing.reference_price
    if ratio <= 0.5:
        return Finding(
            "price_anomaly",
            "fail",
            30,
            f"price {listing.price} is {ratio:.0%} of reference {listing.reference_price}",
        )
    if ratio <= 0.75:
        return Finding(
            "price_anomaly",
            "warn",
            12,
            f"price {listing.price} is {ratio:.0%} of reference {listing.reference_price}",
        )
    return Finding(
        "price_anomaly",
        "pass",
        0,
        f"price {listing.price} is {ratio:.0%} of reference {listing.reference_price}",
    )


def check_completeness(listing: Listing) -> Finding:
    missing: list[str] = []
    if len(listing.body.strip()) < 120:
        missing.append("description under 120 characters")
    if not listing.seller:
        missing.append("no seller identity given")
    if listing.price is None:
        missing.append("no price stated")
    if not missing:
        return Finding("completeness", "pass", 0, "title, description, seller and price present")
    weight = 6 * len(missing)
    return Finding(
        "completeness",
        "warn",
        weight,
        "missing: " + "; ".join(missing),
    )


ALL_CHECKS = [
    check_red_flags,
    check_off_platform_contact,
    check_urgency,
    check_price_anomaly,
    check_completeness,
]


@dataclass
class FactSheet:
    listing: Listing
    findings: list[Finding] = field(default_factory=list)

    @property
    def risk_score(self) -> int:
        return sum(f.weight for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "listing": asdict(self.listing),
            "findings": [asdict(f) for f in self.findings],
            "risk_score": self.risk_score,
        }


def collect_facts(listing: Listing) -> FactSheet:
    """Run every deterministic check over a listing. Pure and repeatable."""
    return FactSheet(listing=listing, findings=[check(listing) for check in ALL_CHECKS])
