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

- Current completed implementation phase: Phase 8B.1.
- Current next phase: Phase 8B.2.
- Phase ledger: `docs/architecture/PHASE_STATUS.md`.
- Architecture baseline: `docs/architecture/PROJECT_BASELINE.md`.
- Frozen rules: `docs/architecture/ARCHITECTURE_INVARIANTS.md`.

Phase 8B.2 is bounded to real JLCEDA design context, provider-neutral design
evidence, recorded hardware evidence, and the deterministic evidence workflow.
It does not authorize real hardware or a real DeepSeek call.

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
