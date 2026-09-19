# Codex Project Context

This file is the operational entry point for work on AI Instrument Assistant.
It summarizes workflow rules; the detailed architecture lives in the linked
documents.

## Before Making Changes

Follow this order for every implementation or architecture task:

1. Read `CODEX.md`.
2. Read `docs/architecture/PROJECT_BASELINE.md`.
3. Read `docs/architecture/ARCHITECTURE_INVARIANTS.md`.
4. Read `docs/architecture/PHASE_STATUS.md`.
5. Read the ADR or validation document for the current phase.
6. Inspect the relevant current code and tests before editing.

Repository state and canonical schemas override stale conversational memory.
If this context pack conflicts with a canonical schema, current code, an
accepted ADR, or current tests, STOP. Issue a **Context Drift / Architecture
Proposal** that identifies the discrepancy and its impact; do not silently
choose one source.

If a requested change conflicts with a frozen invariant, STOP and issue an
**Architecture / Compatibility Proposal** before implementation. Do not
silently weaken tests, validation, evidence semantics, or safety controls to
make a feature pass.

## Current Baseline

- Current completed implementation phase: Phase 8.5A; Phase 8.5B is closed
  for now as a limited integration. Attempts 1–4 remain historical NOT PASS.
- Current completed major phase: Phase 8.
- Current intermediate phase: Phase 8.5B CLOSED FOR NOW / LIMITED INTEGRATION.
- Next major phase: Phase 9 (planned; not started).
- RE-001 current-core milestone: **CORE E2E PROOF COMPLETE**. RE-001A remains
  EDA-provider limited; RE-001B, RE-001C-Lite, and RE-001D-Lite are complete
  within their bounded claims. No next development phase has started.
- Phase ledger: `docs/architecture/PHASE_STATUS.md`.
- Architecture baseline: `docs/architecture/PROJECT_BASELINE.md`.
- Frozen rules: `docs/architecture/ARCHITECTURE_INVARIANTS.md`.

Phase 8.5A established the reviewed authoritative Python Application Host,
generation-scoped sessions, revisioned workflow state, one-time Challenges,
the additive `aia-interactive/v1` frontend contract, reconnect/cancellation,
safe status, and runtime/bootstrap lifecycle seams. Phase 8.5B.0 is reviewed
PASS with official-Dialog UI and separate-listener dispositions. The Phase
8.5B JLCEDA interaction surface now has a minimal production composition from
the interactive listener through the authoritative Host and provider-neutral
EDA path to the separate AIA-JLCEDA provider boundary. Async EDA I/O occurs
outside the Host mutation lock and stale results fail closed. The first real
smoke proved both authenticated connections and real Host-side observations,
but ended NOT PASS on interactive runtime coordination. The approved offline
repair separates snapshot servicing from pending EDA commands and
generation-binds selection callbacks. Attempt 2 proved that an explicit Status
request reaches Python snapshot construction and reply send, but the JLCEDA
Status action still fails before successful client completion. The offline
client repair now completes a same-session explicit waiter before
calling non-authoritative snapshot observers and adds bounded completion-stage
diagnostics. Separately authorized Attempt 3 used v0.2.17 and stopped at Gate
A: the server sent one initial snapshot, but the explicit Status action
produced zero server-side snapshot requests and replies. Subsequent bounded
real diagnostics proved that exported menu functions may run in a different
VM/module context from activation, while private `SYS_MessageBus` reaches the
connected activation-owned Runtime. The uncommitted 0.2.23 repair makes menu
exports thin stubs over one closed private command bridge; offline production
Status and design-observe loopbacks pass. Attempt 4 then bounded the remaining
failure to selection observation. Provider-context diagnostics proved the
canonical object read succeeds when stable and that ID reconstruction is
lossy. The uncommitted 0.2.26 repair removes the competing presentation read
and adds one bounded read-only stabilization retry. Phase 8.5B is now closed
for now as a limited integration: reliable automatic JLCEDA current-selection
capture remains deferred because it is host-state-sensitive in the reviewed
JLCEDA 3.x runtime. Typed candidate binding from that UI capture, trusted
design selection depending on it, and automatic `ProbeTarget` derivation from
it are likewise deferred. No further real run is authorized. Python production
authority is limited to trusted design selection; operation Scope and physical
confirmation remain deferred to their existing Harness TypeScript factories
in Phase 8.5C. No further retry or real JLCEDA, Hardware, VISA, measurement, EDA
mutation, or model action is authorized by this status.

Phase 8B.3 completed its bounded real JLCEDA plus real DS1102Z-E validation.
Phase 8C.1 established the reviewed deterministic claim-policy boundary. It
permits only exact evidence, deterministic comparison, and limitation claim
slots; ALLOW is necessary but not sufficient for publication. Inference,
hypothesis, causal diagnosis, educational knowledge, and next-measurement
proposals remain blocked. SHA-256 identifiers in this boundary are content
identities only, never trust or authority. Phase 8C.2A established the reviewed
deterministic structured publication boundary: Host-owned aliases, a minimal
non-factual candidate, deterministic Grounding/rendering/fallback, and required
final Egress. Phase 8C.2B completed the one-attempt provider-neutral model port,
strict private transport, zero-Tool frozen DeepSeek route, raw Egress precheck,
strict candidate validation, deterministic fallback, canonical rendering, and
independent final Egress. One separately authorized real request passed the
approved safety Case B: the Schema-invalid candidate was discarded and the
deterministic fallback was safely published. A Schema-valid real-model happy
path was not observed. That authorization is consumed; no further real model,
EDA, or Hardware execution is authorized. Phase 9 is roadmap only.

## Implementation Workflow

Before implementation:

1. Read the context pack.
2. Identify the current phase and its exact scope.
3. Inspect the relevant current implementation.
4. Inspect the relevant tests and canonical contracts.
5. Restate the applicable frozen constraints internally.
6. Implement Red -> Green.
7. Run targeted tests.
8. Run the regression suite required by the phase.
9. Stop before committing whenever phase instructions require review.

Use repository-relative documentation links and keep phase evidence bounded.
Do not reconstruct lost measurements, rejected model text, or unreported
runtime outcomes. A later PASS never rewrites an earlier NOT PASS record.

## Default Safety Boundaries

- Do not call a model, JLCEDA, or hardware unless the current task explicitly
  authorizes that external action.
- Tool selection is not Tool authorization.
- EDA selection is not physical probe confirmation.
- Design targets, simulated values, software analysis, and physical facts are
  distinct evidence categories.
- No raw SCPI Tool, generic hardware executor, arbitrary JavaScript execution,
  or automatic REAL-to-SIMULATED fallback is allowed.
- Generated output must preserve the existing operation-scope, physical-policy,
  canonical-evidence, grounding, egress, and runner-failure boundaries.

## Verification Pointers

- Python architecture tests: `tests/architecture/`.
- JLCEDA architecture tests: `extensions/jlceda/tests/architecture/`.
- Harness architecture tests: `extensions/deepseek-harness/tests/architecture/`.
- Unified regression entry: `scripts/run_contract_tests.py`.
- Cross-language wire authorities: `protocols/`.
