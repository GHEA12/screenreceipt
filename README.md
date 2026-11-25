# ScreenReceipt

A scam-screening agent built on the **OpenMinion 0.1 Python SDK** for
Cortensor Hackathon #5. Paste a marketplace listing, rental ad, or job offer;
the agent screens it for scam signals and returns a verdict — and every
screen is sealed into a **hash-chained receipt** that anyone can re-verify
offline, so an agent's verdict can be audited later instead of trusted
blindly.

## The design rule

**The model never collects the facts.** Deterministic tools collect the
evidence; the judge only reasons over the facts and must return a typed
verdict whose every row quotes the evidence it rests on. The receipt hashes
the listing, the facts, and the verdict together and chains to the previous
receipt — edit a recorded verdict afterwards and the chain breaks.

## How the OpenMinion workflow fits together

1. `screenreceipt/facts.py` — five deterministic checks (red-flag phrases,
   off-platform contact lures, urgency language, price anomaly vs a
   reference price, listing completeness). Pure functions; no model, no
   network; each returns pass/warn/fail plus the exact matched evidence.
2. `screenreceipt/agent.py` — the same checks are registered as OpenMinion
   run-scoped decorated tools with explicit permission metadata
   (`@tool(min_scope="READ_ONLY", idempotent=True)`), and an
   `openminion.Agent` is constructed with those tools, `forced_tools`, a
   durable `session_id`, and — in live mode — `output_type=ScreenVerdict`
   (a pydantic model) so the model's verdict has a fixed, auditable shape.
3. `screenreceipt/judge.py` — two interchangeable judges produce the same
   `ScreenVerdict`: a model judge (live mode, via whichever provider the
   OpenMinion config selects — Cortensor Router, Cortensor Portal,
   OpenRouter, …) and a documented deterministic rule judge (mock mode).
4. `screenreceipt/receipts.py` — each run appends a receipt to
   `receipts.jsonl`: listing hash, facts hash, verdict, provider, model,
   mode (`live`/`mock`), previous receipt hash, receipt hash.
   `python screen.py verify` recomputes the whole chain offline.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Credential-free bring-up (documented echo provider):
.venv/bin/openminion config init --provider echo
```

## Run the working example

```bash
# Offline judge + a real OpenMinion echo smoke turn per screen:
.venv/bin/python screen.py screen examples/scam-listing.json
.venv/bin/python screen.py screen examples/legit-listing.json

# Re-verify the receipt ledger:
.venv/bin/python screen.py verify
```

Expected: the scam listing returns **HIGH_RISK**, the legit one **CLEAR**,
and `verify` reports the chain intact. Reports land in `runs/`, facts next
to them, receipts in `receipts.jsonl`.

## Going live with a real model (incl. Cortensor)

Mock mode needs no credentials. For a model-backed run, point the OpenMinion
profile at a real provider and set live mode:

```bash
# Option A: Cortensor Portal (hosted, experimental; needs team access)
.venv/bin/openminion setup --provider cortensor-portal
# Option B: local Cortensor Router node (default model gpt-oss-20b)
#   providers.cortensor in .openminion/agents.json, key env CORTENSOR_API_KEY
# Option C: any OpenAI-compatible provider, e.g. OpenRouter (OPENROUTER_API_KEY)

SCREENRECEIPT_MODE=live \
SCREENRECEIPT_PROVIDER=cortensor-portal \
SCREENRECEIPT_MODEL=<model-name> \
  .venv/bin/python screen.py screen examples/scam-listing.json
```

In live mode the model must return the typed `ScreenVerdict`; if it does
not, the run fails loudly — there is no silent fallback, and the receipt
records `mode: "live"` only for a genuine model verdict.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

21 tests: the five fact checks, judge thresholds and fact/verdict
consistency, receipt chaining and tamper detection, CLI end-to-end over
both examples, and an integration test that initializes a throwaway echo
config and completes a real OpenMinion smoke turn.

## Building blocks tested / what we learned

See [BUILDING_BLOCKS.md](BUILDING_BLOCKS.md) — including three rough edges
found during bring-up (hand-written config rejected by channel authenticity,
profile-name mismatch, session-to-agent stickiness), each with repro steps.

## License

MIT. Built with AI assistance (disclosed per the hackathon's explainability
condition); the entrant can explain and demonstrate every part of this
build — see the walkthrough in BUILDING_BLOCKS.md and the project
SUBMISSION notes.
