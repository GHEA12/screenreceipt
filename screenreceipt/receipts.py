"""Hash-chained receipts for screening runs.

Every run appends one receipt to a JSONL ledger. A receipt binds together
the listing, the facts, and the verdict by hash, and chains to the previous
receipt's hash — so editing any recorded verdict after the fact breaks the
chain and is detectable offline with ``verify_ledger``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .facts import FactSheet
from .judge import ScreenVerdict

GENESIS_HASH = "0" * 64


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass
class Receipt:
    run_id: str
    created_at: str
    listing_sha256: str
    facts_sha256: str
    verdict: str
    risk_score: int
    provider: str
    model: str
    mode: str  # "live" (model judge) | "mock" (offline rule judge)
    prev_receipt_hash: str
    receipt_hash: str = ""

    def signing_payload(self) -> dict:
        d = asdict(self)
        d.pop("receipt_hash", None)
        return d

    def compute_hash(self) -> str:
        return _sha256(_canonical(self.signing_payload()))


def _last_receipt_hash(ledger_path: Path) -> str:
    if not ledger_path.exists():
        return GENESIS_HASH
    last = GENESIS_HASH
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            last = json.loads(line)["receipt_hash"]
    return last


def append_receipt(
    ledger_path: Path,
    *,
    facts: FactSheet,
    verdict: ScreenVerdict,
    provider: str,
    model: str,
    mode: str,
) -> Receipt:
    listing_hash = _sha256(_canonical(facts.listing.__dict__ | {"text": facts.listing.text}))
    facts_hash = _sha256(_canonical(facts.to_dict()))
    receipt = Receipt(
        run_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(timezone.utc).isoformat(),
        listing_sha256=listing_hash,
        facts_sha256=facts_hash,
        verdict=verdict.verdict,
        risk_score=verdict.risk_score,
        provider=provider,
        model=model,
        mode=mode,
        prev_receipt_hash=_last_receipt_hash(ledger_path),
    )
    receipt.receipt_hash = receipt.compute_hash()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(receipt), sort_keys=True) + "\n")
    return receipt


@dataclass
class VerifyResult:
    ok: bool
    checked: int
    failures: list[str] = field(default_factory=list)


def verify_ledger(ledger_path: Path) -> VerifyResult:
    """Recompute every receipt hash and the chain linkage. Any tampering
    with a recorded verdict, score, or hash shows up as a failure."""
    failures: list[str] = []
    if not ledger_path.exists():
        return VerifyResult(ok=False, checked=0, failures=["ledger file not found"])
    prev = GENESIS_HASH
    checked = 0
    for i, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        checked += 1
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            failures.append(f"line {i + 1}: invalid JSON ({exc})")
            continue
        stored_hash = raw.get("receipt_hash", "")
        receipt = Receipt(**raw)
        if receipt.prev_receipt_hash != prev:
            failures.append(f"line {i + 1}: chain break (prev hash mismatch)")
        if receipt.compute_hash() != stored_hash:
            failures.append(f"line {i + 1}: receipt hash mismatch (content was altered)")
        prev = stored_hash
    return VerifyResult(ok=not failures, checked=checked, failures=failures)
