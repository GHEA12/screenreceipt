import json
import tempfile
import unittest
from pathlib import Path

from screenreceipt.facts import Listing, collect_facts
from screenreceipt.judge import rule_judge
from screenreceipt.receipts import GENESIS_HASH, append_receipt, verify_ledger

LISTING = Listing(
    title="Used bike",
    body="Well maintained city bike, meet in person to inspect, cash on delivery is fine.",
    price=300,
    reference_price=320,
    seller="sari_bikes",
)


def _append(ledger: Path):
    facts = collect_facts(LISTING)
    return append_receipt(
        ledger, facts=facts, verdict=rule_judge(facts),
        provider="echo", model="echo", mode="mock",
    )


class TestReceipts(unittest.TestCase):
    def test_chain_links_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "receipts.jsonl"
            r1 = _append(ledger)
            r2 = _append(ledger)
            self.assertEqual(r1.prev_receipt_hash, GENESIS_HASH)
            self.assertEqual(r2.prev_receipt_hash, r1.receipt_hash)
            result = verify_ledger(ledger)
            self.assertTrue(result.ok, result.failures)
            self.assertEqual(result.checked, 2)

    def test_tampered_verdict_breaks_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "receipts.jsonl"
            _append(ledger)
            _append(ledger)
            lines = ledger.read_text(encoding="utf-8").splitlines()
            raw = json.loads(lines[0])
            raw["verdict"] = "CLEAR" if raw["verdict"] != "CLEAR" else "HIGH_RISK"
            lines[0] = json.dumps(raw, sort_keys=True)
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
            result = verify_ledger(ledger)
            self.assertFalse(result.ok)
            self.assertTrue(any("hash mismatch" in f for f in result.failures))

    def test_missing_ledger_fails_cleanly(self):
        result = verify_ledger(Path("/nonexistent/receipts.jsonl"))
        self.assertFalse(result.ok)
        self.assertEqual(result.checked, 0)


if __name__ == "__main__":
    unittest.main()
