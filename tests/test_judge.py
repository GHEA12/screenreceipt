import json
import unittest
from pathlib import Path

from screenreceipt.facts import Listing, collect_facts
from screenreceipt.judge import rule_judge, verdict_for_score

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def load_example(name: str) -> Listing:
    return Listing(**json.loads((EXAMPLES / name).read_text(encoding="utf-8")))


class TestJudge(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(verdict_for_score(0), "CLEAR")
        self.assertEqual(verdict_for_score(19), "CLEAR")
        self.assertEqual(verdict_for_score(20), "CAUTION")
        self.assertEqual(verdict_for_score(49), "CAUTION")
        self.assertEqual(verdict_for_score(50), "HIGH_RISK")
        self.assertEqual(verdict_for_score(120), "HIGH_RISK")

    def test_rule_judge_scam_is_high_risk(self):
        verdict = rule_judge(collect_facts(load_example("scam-listing.json")))
        self.assertEqual(verdict.verdict, "HIGH_RISK")
        self.assertEqual(len(verdict.checks), 5)

    def test_rule_judge_legit_is_clear(self):
        verdict = rule_judge(collect_facts(load_example("legit-listing.json")))
        self.assertEqual(verdict.verdict, "CLEAR")

    def test_rule_judge_rows_match_facts(self):
        facts = collect_facts(load_example("scam-listing.json"))
        verdict = rule_judge(facts)
        for row, finding in zip(verdict.checks, facts.findings):
            self.assertEqual(row.check, finding.check)
            self.assertEqual(row.status, finding.status)
            self.assertEqual(row.note, finding.evidence)
        self.assertEqual(verdict.risk_score, facts.risk_score)


if __name__ == "__main__":
    unittest.main()
