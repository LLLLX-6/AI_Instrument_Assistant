# Phase 8B.1 — Deterministic Design ↔ Measurement Evidence Workflow

Status: implemented for architecture review; not committed.

## Role and boundary

`EngineeringEvidenceWorkflow` is a provider-neutral application orchestrator.
It proves that existing design evidence and existing measurement evidence can be
linked, compared, assembled, and projected deterministically. It does not
diagnose a circuit, choose an absolute source of truth, authorize an operation,
connect a probe, invoke a Tool, or acquire data.

The immutable request supplies:

- user goal and workflow/request correlation identifiers;
- a `DesignEvidenceContext` tied to one `DesignDocument` snapshot;
- explicit `EngineeringTarget` values and their source evidence;
- one candidate `ProbeTarget`;
- an optional reference to already trusted physical-confirmation evidence;
- an existing `TeachingEvidenceContext` and its channel/observation metadata;
- a final assembly time.

The immutable result contains one `EngineeringEvidenceContext` and its faithful
`TeachingDiagnosisContext` projection.

## Frozen orchestration order

The service performs exactly this order:

1. validate design evidence identity and snapshot invariants;
2. validate target source and provenance;
3. evaluate the evidence cross-reference;
4. locate compatible existing measurement evidence;
5. invoke the existing comparator once per compatible target/source pair;
6. invoke the existing assembler;
7. project the structured teaching context.

There is no inference or diagnosis stage. Design/target validation is exposed by
the existing assembler and reused by both direct assembly and the workflow. Unit
conversion, tolerance handling, and comparison behavior remain solely in the
existing deterministic comparator.

## Cross-reference before comparison

The workflow never treats a `ProbeTarget`, selection, label, or
`TeachingEvidenceContext.confirmationState` as trusted physical confirmation.
The separate Phase 7C host reference must match workflow, request correlation,
channel, probe target, canonical target reference, design snapshot, and temporal
order. Missing confirmation produces `INSUFFICIENT_EVIDENCE`; inconsistent
values produce `MISMATCH`. Either state gates every otherwise compatible
comparison to `INDETERMINATE / CROSS_REFERENCE_UNVERIFIED`.

The workflow consumes this trusted record only as linkage evidence. It cannot
mint operation scope, physical confirmation, execution budget, or Tool calls.
More explicitly, it never creates `ProbeSetupConfirmation` or
`TrustedOperationScope`; both remain external Phase 7C host authorities.

## Target/evidence matching and multiple sources

Measurement items are first mapped by the Phase 8A.2 closed semantic label
allowlist to an explicit metric. A target is compared only with items having the
same metric. Frequency is not compared with duty, Vpp, RMS, or period. Unknown
labels remain metric `OTHER`; there is no fuzzy or model-assisted matching.

Every compatible source remains independent. A frequency target with instrument
and software frequency therefore produces two comparison results. The workflow
does not average, rank, prefer, or overwrite either source. FACT,
SOFTWARE_ANALYSIS, and SIMULATED_EVIDENCE categories remain visible.

## Tolerance and missing/conflicting evidence

The workflow supplies targets and observations to the existing comparator
without adding any tolerance. For the recorded PWM fixture:

- target 10 kHz vs instrument 10020 Hz → +0.02 kHz;
- target 10 kHz vs software 10010 Hz → +0.01 kHz;
- target 30 percent vs software ratio 0.2995 → -0.05 percent.

All three are `INDETERMINATE / TOLERANCE_UNSPECIFIED`. With an explicitly
recorded ±1% tolerance, 10.02 kHz is MATCH and 8 kHz is MISMATCH. Neither result
contains a causal explanation.

No target remains an empty target set plus `TARGET_MISSING`. No measurement
remains null plus `MEASUREMENT_MISSING` comparisons. Empty or unavailable
observations remain bounded missing/unavailable results. Conflicting instrument
8.00 kHz and software 8.02 kHz remain two distinct results; 8.01 kHz is never
synthesized.

## Provenance and temporal semantics

The output retains the design document and snapshot, target source evidence,
probe candidate, physical-confirmation reference, workflow/request IDs,
measurement channel/context locator, evidence method/timestamp/algorithm,
comparator name/version, assembler name/version, and assembly time.

Design capture, target declaration, confirmation, measurement, and assembly
times remain separate. Existing `sequential_same_session` coherence is preserved
and never upgraded to simultaneous or atomic.

## Teaching projection and zero inference

The projection contains the goal, design facts, design targets, physical
observations, software analyses, simulated evidence, comparisons, quality,
warnings, coherence, limitations, and unresolved questions. It carries no
diagnosis or causal prose. Both output contexts contain zero generated inference
items.

Candidate next measurements remain empty in Phase 8B.1. No recommendation can
create authorization or execution state. Candidate-next-measurement generation
is deferred to a later reviewed phase.

## Recorded validation scenarios

`tests/fixtures/evidence_workflow/scenarios.json` contains bounded provider-neutral
recordings for PWM without tolerance, explicit tolerance MATCH/MISMATCH, missing
confirmation, channel mismatch, snapshot mismatch, conflicting sources,
unavailable observation, and empty measurement. These are synthetic/recorded
inputs; no model, EDA runtime, instrument, backend, artifact fetch, or network
operation is used.

## Limitations

- Metric selection uses only the approved deterministic locator allowlist.
- Exactly one candidate probe target and one measurement channel are evaluated
  per workflow request in this phase.
- Trusted-confirmation persistence and issuance remain Phase 7C host concerns.
- No source-preference policy, tolerance policy, causal model, diagnostic text,
  next-measurement generation, artifact inspection, or physical execution is
  implemented.
