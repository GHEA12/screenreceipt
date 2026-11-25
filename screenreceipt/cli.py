"""ScreenReceipt CLI.

Usage:
  python screen.py screen examples/scam-listing.json
  python screen.py screen listing.txt --price 250 --reference-price 900
  python screen.py verify            # re-check the receipt ledger
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import Settings, screen_listing
from .facts import Listing, collect_facts
from .receipts import append_receipt, verify_ledger


def load_listing(path: Path, args: argparse.Namespace) -> Listing:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(raw)
        listing = Listing(
            title=data.get("title", ""),
            body=data.get("body", ""),
            price=data.get("price"),
            reference_price=data.get("reference_price"),
            seller=data.get("seller", ""),
        )
    else:
        lines = raw.splitlines()
        listing = Listing(title=lines[0] if lines else "", body="\n".join(lines[1:]))
    if args.price is not None:
        listing.price = args.price
    if args.reference_price is not None:
        listing.reference_price = args.reference_price
    if args.seller is not None:
        listing.seller = args.seller
    return listing


def render_report(listing: Listing, outcome, receipt) -> str:
    v = outcome.verdict
    lines = [
        f"# ScreenReceipt report — {v.verdict} (risk score {v.risk_score})",
        "",
        f"Listing: {listing.title or '(untitled)'}",
        f"Judge: {outcome.mode} mode via provider '{outcome.provider}'"
        + (f" / model '{outcome.model}'" if outcome.model else "")
        + f"; OpenMinion smoke turn: {outcome.smoke}",
        "",
        v.summary,
        "",
        "| Check | Status | Note |",
        "| --- | --- | --- |",
    ]
    for row in v.checks:
        note = row.note.replace("|", "\\|")
        lines.append(f"| {row.check} | {row.status} | {note} |")
    lines += [
        "",
        f"Receipt: run `{receipt.run_id}`, hash `{receipt.receipt_hash[:16]}…`, "
        f"chained to `{receipt.prev_receipt_hash[:16]}…`. "
        "Re-verify the whole ledger with `python screen.py verify`.",
    ]
    return "\n".join(lines) + "\n"


def cmd_screen(args: argparse.Namespace) -> int:
    listing = load_listing(Path(args.input), args)
    settings = Settings.from_env()
    if args.no_smoke:
        settings.run_smoke = False
    outcome = screen_listing(listing, settings)
    facts = collect_facts(listing)
    ledger = Path(args.ledger)
    receipt = append_receipt(
        ledger,
        facts=facts,
        verdict=outcome.verdict,
        provider=outcome.provider,
        model=outcome.model,
        mode=outcome.mode,
    )
    report = render_report(listing, outcome, receipt)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"report-{receipt.run_id}.md").write_text(report, encoding="utf-8")
    (out_dir / f"facts-{receipt.run_id}.json").write_text(
        json.dumps(facts.to_dict(), indent=2), encoding="utf-8"
    )
    print(report)
    print(f"[ledger] appended receipt {receipt.run_id} to {ledger}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    result = verify_ledger(Path(args.ledger))
    if result.ok:
        print(f"OK: {result.checked} receipt(s) verified, chain intact.")
        return 0
    print(f"FAILED: {result.checked} receipt(s) checked, {len(result.failures)} problem(s):")
    for failure in result.failures:
        print(f"  - {failure}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="screenreceipt")
    sub = parser.add_subparsers(dest="command", required=True)

    p_screen = sub.add_parser("screen", help="screen one listing")
    p_screen.add_argument("input", help="listing file (.json or .txt)")
    p_screen.add_argument("--price", type=float, default=None)
    p_screen.add_argument("--reference-price", type=float, default=None)
    p_screen.add_argument("--seller", default=None)
    p_screen.add_argument("--ledger", default="receipts.jsonl")
    p_screen.add_argument("--out", default="runs")
    p_screen.add_argument("--no-smoke", action="store_true",
                          help="skip the OpenMinion echo smoke turn in mock mode")
    p_screen.set_defaults(func=cmd_screen)

    p_verify = sub.add_parser("verify", help="re-verify the receipt ledger")
    p_verify.add_argument("--ledger", default="receipts.jsonl")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
