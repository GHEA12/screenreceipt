"""Integration test: the OpenMinion SDK wiring really runs.

Initializes a throwaway OpenMinion config with the credential-free echo
provider (the documented bring-up path), then screens a listing through
screen_listing() and asserts the OpenMinion smoke turn completed. Skipped
when the openminion package is not installed.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import openminion  # noqa: F401
    HAVE_OPENMINION = True
except ImportError:
    HAVE_OPENMINION = False

from screenreceipt.agent import Settings, screen_listing
from screenreceipt.facts import Listing

LISTING = Listing(
    title="Used bike",
    body="Well maintained city bike, meet in person to inspect, cash on delivery is fine.",
    price=300,
    reference_price=320,
    seller="sari_bikes",
)


@unittest.skipUnless(HAVE_OPENMINION, "openminion not installed")
class TestOpenMinionSmoke(unittest.TestCase):
    def test_echo_smoke_turn_completes(self):
        exe = shutil.which("openminion") or str(Path(sys.executable).parent / "openminion")
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            proc = subprocess.run(
                [exe, "config", "init", "--provider", "echo"],
                cwd=workdir, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            settings = Settings(mode="mock", provider="echo", model="echo",
                                config_dir=workdir, agent_id="openminion")
            outcome = screen_listing(LISTING, settings)
            self.assertEqual(outcome.smoke, "ok", outcome.smoke)
            self.assertEqual(outcome.mode, "mock")
            self.assertIn(outcome.verdict.verdict, ("CLEAR", "CAUTION", "HIGH_RISK"))


if __name__ == "__main__":
    unittest.main()
