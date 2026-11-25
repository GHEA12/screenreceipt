import json
import unittest
from pathlib import Path

from screenreceipt.facts import (
    Listing,
    check_completeness,
    check_off_platform_contact,
    check_price_anomaly,
    check_red_flags,
    check_urgency,
    collect_facts,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def load_example(name: str) -> Listing:
    data = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return Listing(**data)


class TestChecks(unittest.TestCase):
    def test_red_flags_hit_on_scam_phrases(self):
        listing = Listing(title="Deal", body="Send a deposit first, payment in advance, gift cards accepted.")
        f = check_red_flags(listing)
        self.assertEqual(f.status, "fail")
        self.assertGreaterEqual(f.weight, 25)
        self.assertIn("deposit", f.evidence)

    def test_red_flags_pass_on_clean_text(self):
        listing = Listing(title="Bike", body="Well maintained city bike, meet in person to inspect.")
        f = check_red_flags(listing)
        self.assertEqual(f.status, "pass")
        self.assertEqual(f.weight, 0)

    def test_off_platform_lure(self):
        listing = Listing(title="x", body="Message me on WhatsApp, contact me outside the app.")
        f = check_off_platform_contact(listing)
        self.assertEqual(f.status, "fail")
        self.assertGreaterEqual(f.weight, 20)

    def test_urgency_warns(self):
        listing = Listing(title="x", body="Act now, today only, first come first served!")
        f = check_urgency(listing)
        self.assertEqual(f.status, "warn")
        self.assertGreater(f.weight, 0)

    def test_price_anomaly_deep_discount_fails(self):
        listing = Listing(title="x", body="y", price=100, reference_price=1000)
        f = check_price_anomaly(listing)
        self.assertEqual(f.status, "fail")
        self.assertEqual(f.weight, 30)

    def test_price_anomaly_fair_price_passes(self):
        listing = Listing(title="x", body="y", price=820, reference_price=900)
        self.assertEqual(check_price_anomaly(listing).status, "pass")

    def test_price_anomaly_skips_without_pair(self):
        listing = Listing(title="x", body="y")
        f = check_price_anomaly(listing)
        self.assertEqual(f.status, "pass")
        self.assertEqual(f.detail, "skipped")

    def test_completeness_flags_thin_listing(self):
        listing = Listing(title="x", body="short")
        f = check_completeness(listing)
        self.assertEqual(f.status, "warn")
        self.assertGreater(f.weight, 0)

    def test_collect_facts_scam_example_scores_high(self):
        facts = collect_facts(load_example("scam-listing.json"))
        self.assertGreaterEqual(facts.risk_score, 50)
        self.assertEqual(len(facts.findings), 5)

    def test_collect_facts_legit_example_scores_low(self):
        facts = collect_facts(load_example("legit-listing.json"))
        self.assertLess(facts.risk_score, 20)

    def test_collect_facts_is_deterministic(self):
        listing = load_example("scam-listing.json")
        self.assertEqual(collect_facts(listing).to_dict(), collect_facts(listing).to_dict())


if __name__ == "__main__":
    unittest.main()
