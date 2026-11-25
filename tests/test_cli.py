import json
import os
import tempfile
import unittest
from pathlib import Path

from screenreceipt.cli import main
from screenreceipt.receipts import verify_ledger

PROJECT = Path(__file__).resolve().parent.parent


class TestCliEndToEnd(unittest.TestCase):
    def test_screen_examples_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = str(Path(tmp) / "receipts.jsonl")
            out = str(Path(tmp) / "runs")
            env = dict(os.environ, SCREENRECEIPT_MODE="mock")
            old = os.environ.copy()
            os.environ.update(env)
            try:
                rc = main([
                    "screen", str(PROJECT / "examples" / "scam-listing.json"),
                    "--ledger", ledger, "--out", out, "--no-smoke",
                ])
                self.assertEqual(rc, 0)
                rc = main([
                    "screen", str(PROJECT / "examples" / "legit-listing.json"),
                    "--ledger", ledger, "--out", out, "--no-smoke",
                ])
                self.assertEqual(rc, 0)
            finally:
                os.environ.clear()
                os.environ.update(old)

            result = verify_ledger(Path(ledger))
            self.assertTrue(result.ok, result.failures)
            self.assertEqual(result.checked, 2)

            rows = [json.loads(l) for l in Path(ledger).read_text().splitlines()]
            self.assertEqual(rows[0]["verdict"], "HIGH_RISK")
            self.assertEqual(rows[1]["verdict"], "CLEAR")
            self.assertEqual(rows[0]["mode"], "mock")
            reports = list(Path(out).glob("report-*.md"))
            self.assertEqual(len(reports), 2)

    def test_screen_text_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "listing.txt"
            txt.write_text(
                "Cheap phones, act now\nSend a deposit first by wire transfer, gift cards ok.",
                encoding="utf-8",
            )
            rc = main([
                "screen", str(txt),
                "--ledger", str(Path(tmp) / "r.jsonl"),
                "--out", str(Path(tmp) / "runs"), "--no-smoke",
            ])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
