# AI Instrument Assistant — Architecture Invariants

These are frozen constraints at repository baseline `76502f9`. Terms such as
MUST and MUST NOT are normative. A conflicting request requires an Architecture
/ Compatibility Proposal before implementation.

## 1. General Layering and Contracts

- Domain code MUST NOT depend on Harness, DeepSeek, VISA, SCPI, Rigol, JLCEDA,
  vendor SDKs, transports, or concrete adapters.
- Application services MUST depend on provider-neutral ports/interfaces rather
  than concrete drivers or vendor runtimes.
- Vendor-specific wire, SDK, runtime, and command details MUST remain at
  adapter, integration, communication, or driver boundaries.
- Higher layers MUST NOT directly issue vendor-specific commands.
- Official JLCEDA `eda.*` objects MUST be normalized at the TypeScript adapter
  boundary and MUST NOT enter Python domain models.
- JSON Schema MUST remain the cross-language wire-format authority where a
  canonical contract exists. Language bindings MUST NOT redefine competing
  field or operation contracts.
- Protocol state, authentication, correlation, nonce, replay, and session rules
  MUST remain separate from single-message Schema validation.

## 2. Agent Execution Safety

The frozen governance controls are independent and cumulative:

1. `TrustedOperationScope` defines which semantic operations the trusted
   user/host workflow authorizes.
2. Physical Policy determines whether real physical execution is confirmed and
   safe.
3. Canonical Hardware evidence and `TeachingEvidenceContext` record what was
   actually observed or analyzed.
4. Grounding Guard determines which claims may be made from that evidence.
5. Egress Guard determines which model-authored content may be displayed or
   persisted.
6. Runner Failure Boundary keeps validation and process failures bounded.

- Tool selection MUST NOT be treated as Tool authorization.
- Prompt guidance MUST NOT be treated as deterministic enforcement.
- Model text, Tool arguments, Tool results, or simulated mode MUST NOT create,
  widen, renew, or recover a `TrustedOperationScope`.
- LLM free text MUST NOT create a `ProbeSetupConfirmation`.
- The model MUST NOT switch a requested REAL backend to SIMULATED.
- Missing or unknown trusted scope MUST fail closed.
- Scope denial MUST produce zero Physical Policy evaluation, zero IPC, and zero
  hardware side effect.
- The execution order MUST remain: Schema validation -> operation-scope
  preflight -> Physical Policy -> final scope authorization/budget consumption
  -> IPC.
- A scope budget MUST be consumed only at final pre-IPC authorization. Denied
  operations MUST NOT consume budget; dispatched or indeterminate operations
  MUST NOT be automatically refunded.
- Failure MUST NOT trigger automatic model retry, Tool retry, IPC replay, or
  physical remeasurement.
- The current scope budget ledger MUST be described as process-local, never as
  durable production authorization.

## 3. Hardware Boundary

Exactly five model-facing semantic Hardware Tools currently exist:

- `hardware_get_status` -> `hardware.get_status`
- `hardware_measure_frequency` -> `hardware.measure_frequency`
- `hardware_measure_vpp` -> `hardware.measure_vpp`
- `hardware_capture_waveform` -> `hardware.capture_waveform`
- `hardware_measure_pwm` -> `hardware.measure_pwm`

- A raw SCPI Tool MUST NOT exist.
- A generic hardware executor or raw operation passthrough MUST NOT exist.
- REAL execution MUST NOT automatically fall back to SIMULATED.
- A canonical Hardware `ok=false` response MUST remain a Tool value; it MUST NOT
  be silently converted into an adapter failure.
- Sent-but-unconfirmed execution MUST NOT be automatically replayed.
- A waveform `ArtifactReference` MUST remain opaque at Tool and Agent
  boundaries.
- Full waveform sample arrays MUST NOT cross the Tool boundary.
- Instrument serial numbers MUST be masked in canonical Tool output.
- Domain and Driver internals MAY retain the real serial when required for
  device identity; that does not authorize disclosure.

## 4. Physical Confirmation

- EDA selection MUST NOT be treated as physical probe confirmation.
- `ProbeTarget` MUST mean only a design-side candidate target.
- Verified physical linkage MUST require trusted user/host confirmation outside
  the EDA selection and teaching-text surfaces.
- Physical confirmation MUST be scoped to channel, target,
  workflow/request correlation, and wiring state.
- A wiring change MUST invalidate the previous physical confirmation.
- Missing trusted confirmation MUST NOT be replaced by
  `TeachingEvidenceContext` text, model prose, label equality, or inferred
  circuit context.

Current enforcement note: `ProbeSetupConfirmation.scope.workflowId` is present
in the model, but the Physical Policy evaluator currently compares only the
confirmation request correlation. The independent operation-scope gate checks
its own workflow. This is an open Context Drift, not an exception to the
invariant; code changes or broader claims in this area require an Architecture
/ Compatibility Proposal and explicit tests.

## 5. Evidence Categories

The following categories MUST remain distinct:

- `DESIGN_FACT`
- `DESIGN_TARGET`
- `PHYSICAL_FACT`
- `SOFTWARE_ANALYSIS`
- `SIMULATED_EVIDENCE`
- `INFERENCE`

- A design target MUST NOT become a measured fact.
- Software analysis MUST NOT become an instrument fact.
- Simulated evidence MUST NOT become a physical fact.
- Missing or unavailable evidence MUST remain missing or unavailable; zero or a
  default MUST NOT be fabricated.
- Conflicting evidence MUST remain separate by source.
- Conflicting sources MUST NOT be averaged or collapsed into a synthetic
  "truth."
- `EngineeringEvidenceContext` MUST remain a composed view, not a new fact
  source.

## 6. Deterministic Comparison

- Comparison MUST NOT be represented as diagnosis or causal explanation.
- Metric matching, unit conversion, and tolerance evaluation MUST be
  deterministic and allowlisted; fuzzy or LLM metric matching MUST NOT be used.
- No engineering tolerance MAY be invented.
- Without explicit tolerance, a numeric difference MAY be computed, but MATCH
  or MISMATCH MUST NOT be emitted. The result MUST be
  `INDETERMINATE / TOLERANCE_UNSPECIFIED`.
- Only explicit tolerance or explicit inclusive bounds MAY produce MATCH or
  MISMATCH.
- Target provenance and tolerance provenance MUST remain explicit.
- Instrument and software observations MUST be compared separately.

## 7. Design-to-Measurement Cross-Reference

- Cross-reference MUST be evaluated before authoritative comparison.
- A `VERIFIED_LINK` MUST require trusted evidence for the candidate
  `ProbeTarget`, physical confirmation, channel match, workflow/request match,
  design snapshot match, and temporal consistency.
- Label or name equality alone MUST NOT establish a verified link.
- Missing trusted linkage MUST gate comparison to a bounded indeterminate
  result.
- The evidence workflow MUST NOT create physical confirmation or
  `TrustedOperationScope`.

## 8. Grounding

- Egress SAFE MUST NOT imply Grounding SUPPORTED.
- Grounding SUPPORTED MUST NOT replace Egress safety.
- `TeachingEvidenceContext` MUST remain the Grounding source of truth.
- Numeric claims MUST use the same metric and correct source and MUST match via
  exact provenance, deterministic approved unit conversion, and approved
  deterministic display rounding.
- Arbitrary numerical-closeness tolerance MUST NOT be used for grounding.
- Instrument evidence MUST be presented as FACT, software analysis as ANALYSIS,
  and simulated evidence as SIMULATED.
- A design target MUST remain context, not measurement evidence.
- An opaque artifact reference MUST NOT imply raw sample access.
- Degraded or failed evidence MUST NOT be upgraded to good, reliable, or
  successful.
- Material warnings MUST NOT be silently omitted from confident conclusions.
- Sequential same-session observations MUST NOT be described as simultaneous
  or atomic.
- Unsupported model output MUST be discarded and repaired only through a
  deterministic fallback that independently passes Egress and Grounding.
- Grounding failure MUST cause zero model retry, zero Tool retry, and zero
  hardware remeasurement.
- The current Grounding Guard MUST be described as validating a constrained
  English claim surface. Ambiguous or unrecognized free-form claims MUST fail
  closed.

## 9. Egress

- Model-generated content MUST remain untrusted until inspected at the egress
  boundary.
- The egress boundary MUST block credential material, absolute host paths, full
  serials, VISA resource identifiers, executable raw instrument-command
  content, waveform sample arrays, and oversized output.
- Egress enforcement MUST NOT degrade into broad keyword filtering.
- Conceptual discussion of SCPI MUST remain allowed; actual command-shaped
  content MUST remain blocked from the governed output surface.
- Rejected raw model content, exception stacks, secrets, and local paths MUST
  NOT enter persisted validation output.

## 10. Phase 8 Evidence Views

- `EngineeringEvidenceContext` MUST remain immutable and MUST NOT become a fact
  source, authorization object, or execution context.
- `TeachingDiagnosisContext` MUST remain an evidence-only projection. Its name
  MUST NOT be interpreted as proof that diagnosis exists.
- `TeachingDiagnosisContext` MUST NOT authorize or execute Tools.
- Current deterministic Phase 8 components MUST generate zero `INFERENCE`.
- `candidate_next_measurements` MUST remain empty/deferred until a later phase
  explicitly designs and reviews it.
- Phase 8B.1 workflow ordering MUST remain: design/target validation ->
  cross-reference -> measurement evidence selection -> comparator -> assembler
  -> teaching projection.

## 11. Historical Validation Integrity

- Historical NOT PASS records MUST remain unchanged as historical evidence.
- A later fix or PASS MUST create a new validation record rather than rewriting
  a failed run.
- Lost measurements, discarded model output, unreported runtime outcomes, and
  unknown execution counts MUST NOT be reconstructed.
- A validation claim MUST remain bounded to the recorded device, workflow,
  environment, authority, and observations.

## 12. Change and Test Discipline

- A new capability MUST begin with the current phase's Red -> Green tests.
- Tests or safety semantics MUST NOT be weakened merely to accept a new feature.
- Architecture enforcement SHOULD use AST/import/module-boundary/schema or
  behavior tests. Plain keyword grep MUST NOT be the primary architecture test.
- Changes to canonical schema semantics, evidence categories, Tool authority,
  physical confirmation, or guard ordering MUST trigger explicit architecture
  review.
- If this document conflicts with canonical schema, current code, accepted ADR,
  or current tests, work MUST STOP and produce a Context Drift / Architecture
  Proposal.

See [PROJECT_BASELINE.md](PROJECT_BASELINE.md) for the subsystem map and
[PHASE_STATUS.md](PHASE_STATUS.md) for the current phase.
