# Building Blocks Tested — ScreenReceipt (OpenMinion 0.1.22)

Environment: Linux VM, Python 3.12.3, `pip install "openminion==0.1.22"`,
no GPU, no Cortensor Portal access (not yet coordinated), no local Router
node. Everything below was run hands-on during the build, 2026-11-25.

## What we used

| Building block | How ScreenReceipt uses it | Verdict |
| --- | --- | --- |
| Python SDK `Agent` | Context-managed agent per screen, `instructions`, `session_id`, `agent_id` | Works |
| Run-scoped decorated tools | Five fact checks as `@tool(min_scope="READ_ONLY", idempotent=True)` functions, exposed only for the run | Works |
| Forced tools | `forced_tools=[...]` with all five tool names so a model judge must call every check | Accepted by the SDK (needs a tool-calling model to observe end-to-end; echo does not call tools) |
| Typed output | `output_type=ScreenVerdict` (pydantic) in live mode | Wired; not yet exercised against a live model (no provider access on this machine) |
| Sessions | One session per screen; session state persisted in `.openminion/state/openminion.db` | Works, with finding #3 below |
| Provider abstraction | Same agent code against `echo` today; `cortensor` / `cortensor-portal` / `openrouter` are pure config changes | Works as documented |
| Config init CLI | `openminion config init --provider echo` generates a complete, working `agents.json` | Works — and is effectively mandatory (finding #1) |
| CLI run path | `openminion run "hello"` against the echo provider | Works |

## Findings (the useful part)

### 1. A hand-written minimal config is rejected at runtime, with a misleading error

Repro: write the providers-doc-shaped minimal config
(`{"default_agent": "default", "agents": {"default": {"provider": "echo"}}, "providers": {"echo": {"model": "echo"}}}`)
and pass it as `Agent(config_path=...)`, then `agent.run("Check A-104")`.
Expected: the documented SDK example runs.
Actual: `RuntimeError: inbound authenticity denied (reason=invalid_channel, mode=warn)`
raised from `services/gateway/security.py`. The minimal config has no
`channel_authenticity` / `enabled_channels` sections, and the default SDK
turn apparently arrives on a channel the runtime does not trust. The error
message never mentions config completeness, so a new SDK user burns time in
the security layer. The fix is to always start from `openminion config
init` (which generates the full config), but the docs' "Basic configuration
pattern" implies the small shape is sufficient. Suggestion: either accept
the minimal shape for SDK turns, or raise a config-validation error naming
the missing sections.

### 2. The initialized profile is named `openminion`, not `default`

Repro: `openminion config init --provider echo`, then construct
`Agent(...)` without `agent_id` (the docs' examples imply a default agent).
Actual: `UnknownProfileError: Unknown agent profile 'default'. Valid profiles: 'openminion'.`
The error message is good (it lists valid profiles), but the docs' Python
SDK example never mentions `agent_id`, so the first SDK run after the
documented CLI init fails. Suggestion: have `config init` also register the
profile under `default`, or show `agent_id="openminion"` in the SDK example.

### 3. Sessions are sticky to the first agent that touches them — including failed runs

Repro: run the docs' example with `session_id="demo"` against a broken
config (finding #1). The run fails. Fix the config/agent, retry with the
same `session_id="demo"`.
Actual: `TurnRequestError: Session 'demo' belongs to agent 'default', not 'openminion'; use a new session_id for 'openminion'.`
A failed first attempt permanently binds the session to the wrong agent.
The error message is admirably explicit, but the binding surviving a failed
turn is surprising. Suggestion: bind the session to the agent on the first
*successful* turn, or mention the stickiness in the SDK quickstart.

### 4. The echo provider does not exercise tools (by design, but worth stating)

With the echo provider, `agent.run(...)` returns `openminion: <message>`
and decorated tools are registered but never invoked — expected for a
bring-up provider, but it means the credential-free path cannot demonstrate
forced-tool behaviour. A deterministic "scripted" test provider that calls
the forced tools in order would make SDK demos and CI far more convincing
without any model. (We worked around it by having the offline judge call
the same underlying check functions the tools wrap, and recording honestly
in each receipt whether the verdict came from a model or the rule judge.)

## What we learned

- Start every OpenMinion project with `config init`/`setup`, never a
  hand-written config; treat the generated `agents.json` as the source of
  truth for profile names.
- Session IDs are durable identities, not labels: namespace them per agent
  and per purpose from day one.
- The permission metadata on tools (`min_scope`, `idempotent`, `dangerous`)
  is the right granularity for a screening agent: all five of our tools are
  read-only and idempotent, and the design rule "the model never collects
  facts" maps cleanly onto registering *only* fact tools plus a typed
  output schema.
- Provider switching really is config-only. The same agent code is ready
  for the Cortensor Router/Portal the moment access exists; nothing in our
  runtime path mentions a vendor.
- For agent outputs people may rely on, bind the verdict to its evidence:
  typed output + hashed facts + a hash-chained receipt turned "the agent
  said so" into something a third party can re-verify offline.
