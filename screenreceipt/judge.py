"""The judge step: turn a FactSheet into a typed verdict.

Two interchangeable judges produce the same ScreenVerdict shape:

- ``rule_judge`` — the offline judge. Deterministic scoring over the facts.
  Used when no model provider is configured; receipts record mode "mock".
- A model judge (see agent.py) — an OpenMinion Agent run whose typed output
  is a ScreenVerdict. Receipts record mode "live" plus provider and model.

Keeping the verdict schema identical is what makes a model verdict auditable
against the same facts a human can re-check.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .facts import FactSheet

HIGH_RISK_THRESHOLD = 50
CAUTION_THRESHOLD = 20


class CheckVerdict(BaseModel):
    check: str
    status: Literal["pass", "warn", "fail"]
    note: str = Field(description="One line tying this verdict row to the fact evidence.")


class ScreenVerdict(BaseModel):
    verdict: Literal["CLEAR", "CAUTION", "HIGH_RISK"]
    risk_score: int
    summary: str
    checks: list[CheckVerdict]


def verdict_for_score(score: int) -> Literal["CLEAR", "CAUTION", "HIGH_RISK"]:
    if score >= HIGH_RISK_THRESHOLD:
        return "HIGH_RISK"
    if score >= CAUTION_THRESHOLD:
        return "CAUTION"
    return "CLEAR"


def rule_judge(facts: FactSheet) -> ScreenVerdict:
    """Deterministic offline judge: the documented fallback when no model
    provider is available. Same thresholds a model judge is instructed to
    respect, applied mechanically."""
    score = facts.risk_score
    verdict = verdict_for_score(score)
    flagged = [f for f in facts.findings if f.status != "pass"]
    if flagged:
        summary = (
            f"{len(flagged)} of {len(facts.findings)} checks flagged this listing "
            f"(risk score {score}). Strongest signal: {flagged[0].check} — {flagged[0].evidence}."
        )
    else:
        summary = f"All {len(facts.findings)} checks passed (risk score {score})."
    return ScreenVerdict(
        verdict=verdict,
        risk_score=score,
        summary=summary,
        checks=[
            CheckVerdict(check=f.check, status=f.status, note=f.evidence)
            for f in facts.findings
        ],
    )
