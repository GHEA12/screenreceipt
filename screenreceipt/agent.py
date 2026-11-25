"""OpenMinion wiring for ScreenReceipt.

The fact checks from facts.py are exposed to an OpenMinion Agent as
run-scoped decorated tools with explicit permission metadata
(``min_scope="READ_ONLY"``, ``idempotent=True``). The agent is asked for a
typed ``ScreenVerdict`` (pydantic), so a model verdict has exactly the same
shape as the offline rule judge's verdict and can be audited against the
same facts.

Provider selection is OpenMinion config, not code: the agent profile in the
working directory's ``.openminion/agents.json`` decides whether inference is
the credential-free ``echo`` bring-up provider, a local Cortensor Router,
the hosted Cortensor Portal, OpenRouter, etc. This module only labels the
receipt with the provider/model names from the environment so a run record
says honestly what produced the verdict.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .facts import (
    Listing,
    check_completeness,
    check_off_platform_contact,
    check_price_anomaly,
    check_red_flags,
    check_urgency,
    collect_facts,
)
from .judge import ScreenVerdict, rule_judge

INSTRUCTIONS = """You are ScreenReceipt, a scam-screening agent.
You never collect facts yourself and you never invent evidence.
For the listing in the user message, call every screening tool once, then
return a ScreenVerdict: verdict CLEAR below a risk score of 20, CAUTION from
20 to 49, HIGH_RISK at 50 or above. risk_score is the sum of the tool
weights. Each checks row must quote the tool's evidence in its note."""


@dataclass
class Settings:
    mode: str = "mock"  # "mock" (offline rule judge) | "live" (model judge)
    provider: str = "echo"
    model: str = "echo"
    config_dir: Path = field(default_factory=Path.cwd)
    agent_id: str = "openminion"
    run_smoke: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mode=os.environ.get("SCREENRECEIPT_MODE", "mock"),
            provider=os.environ.get("SCREENRECEIPT_PROVIDER", "echo"),
            model=os.environ.get("SCREENRECEIPT_MODEL", "echo"),
            config_dir=Path(os.environ.get("OPENMINION_CONFIG_DIR", ".")),
            agent_id=os.environ.get("OPENMINION_AGENT_ID", "openminion"),
            run_smoke=os.environ.get("SCREENRECEIPT_SMOKE", "1") != "0",
        )


def build_tools():
    """Register the deterministic checks as OpenMinion tools.

    Imported lazily so the core package (facts/judge/receipts) works and is
    testable without the SDK installed.
    """
    from openminion import tool

    @tool(min_scope="READ_ONLY", idempotent=True)
    def scan_red_flags(text: str) -> str:
        """Scan listing text for known scam phrases. Returns JSON finding."""
        f = check_red_flags(Listing(title="", body=text))
        return json.dumps(f.__dict__)

    @tool(min_scope="READ_ONLY", idempotent=True)
    def scan_off_platform_contact(text: str) -> str:
        """Detect lures that move the conversation off the platform."""
        f = check_off_platform_contact(Listing(title="", body=text))
        return json.dumps(f.__dict__)

    @tool(min_scope="READ_ONLY", idempotent=True)
    def scan_urgency_language(text: str) -> str:
        """Detect pressure/urgency language in listing text."""
        f = check_urgency(Listing(title="", body=text))
        return json.dumps(f.__dict__)

    @tool(min_scope="READ_ONLY", idempotent=True)
    def check_price(price: float, reference_price: float) -> str:
        """Compare the asking price against a reference market price."""
        f = check_price_anomaly(
            Listing(title="", body="", price=price, reference_price=reference_price)
        )
        return json.dumps(f.__dict__)

    @tool(min_scope="READ_ONLY", idempotent=True)
    def check_listing_completeness(body: str, seller: str, has_price: bool) -> str:
        """Check the listing carries the basics a buyer needs to verify it."""
        f = check_completeness(
            Listing(title="", body=body, seller=seller, price=1.0 if has_price else None)
        )
        return json.dumps(f.__dict__)

    return [
        scan_red_flags,
        scan_off_platform_contact,
        scan_urgency_language,
        check_price,
        check_listing_completeness,
    ]


TOOL_NAMES = [
    "scan_red_flags",
    "scan_off_platform_contact",
    "scan_urgency_language",
    "check_price",
    "check_listing_completeness",
]


@dataclass
class ScreenOutcome:
    verdict: ScreenVerdict
    mode: str  # "live" | "mock"
    provider: str
    model: str
    smoke: str = "skipped"  # "ok" | "failed: ..." | "skipped"
    agent_text: str = ""


def _openminion_agent_run(listing: Listing, settings: Settings, *, typed: bool):
    """Run one OpenMinion Agent turn for this listing inside the configured
    working directory (OpenMinion discovers .openminion/agents.json from the
    current directory). Returns the AgentRunResult."""
    from openminion import Agent

    tools = build_tools()
    kwargs = dict(
        instructions=INSTRUCTIONS,
        tools=tools,
        forced_tools=TOOL_NAMES,
        session_id=f"screenreceipt-{os.getpid()}",
        agent_id=settings.agent_id,
    )
    if typed:
        kwargs["output_type"] = ScreenVerdict
    cwd = Path.cwd()
    os.chdir(settings.config_dir)
    try:
        with Agent(**kwargs) as agent:
            return agent.run(
                "Screen this listing and return the verdict.\n"
                f"TITLE: {listing.title}\nBODY: {listing.body}\n"
                f"PRICE: {listing.price} REFERENCE_PRICE: {listing.reference_price}\n"
                f"SELLER: {listing.seller}"
            )
    finally:
        os.chdir(cwd)


def screen_listing(listing: Listing, settings: Settings) -> ScreenOutcome:
    """Screen one listing.

    Live mode: the model judge runs through OpenMinion and must return a
    typed ScreenVerdict; any failure raises (no silent fallback).
    Mock mode: an OpenMinion smoke turn under the echo provider proves the
    SDK wiring (session, tool registration, forced tools), and the verdict
    comes from the deterministic rule judge. The receipt records which.
    """
    facts = collect_facts(listing)
    if settings.mode == "live":
        result = _openminion_agent_run(listing, settings, typed=True)
        verdict = result.output
        if not isinstance(verdict, ScreenVerdict):
            raise RuntimeError(
                f"model judge did not return a ScreenVerdict (got {type(verdict).__name__})"
            )
        return ScreenOutcome(
            verdict=verdict,
            mode="live",
            provider=settings.provider,
            model=settings.model,
            smoke="n/a",
            agent_text=result.text or "",
        )

    smoke = "skipped"
    agent_text = ""
    if settings.run_smoke:
        try:
            result = _openminion_agent_run(listing, settings, typed=False)
            smoke = "ok"
            agent_text = result.text or ""
        except Exception as exc:  # smoke is diagnostic; verdict path is offline
            smoke = f"failed: {type(exc).__name__}: {exc}"
    return ScreenOutcome(
        verdict=rule_judge(facts),
        mode="mock",
        provider=settings.provider,
        model=settings.model,
        smoke=smoke,
        agent_text=agent_text,
    )
