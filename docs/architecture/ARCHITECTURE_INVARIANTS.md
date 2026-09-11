# AI Instrument Assistant — Architecture Invariants

These are frozen constraints established through the current reviewed project
baseline. Terms such as
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

## 4. Trusted Design Selection Disambiguation

- Provider-observed selection and trusted user disambiguation MUST remain
  separate provenance.
- Provider `primary_object` MUST remain null unless the provider itself supplies
  documented primary evidence.
- A trusted design decision MAY select only an exact candidate already present
  in the current bounded provider observation.
- Candidate identity MUST use provider, document, snapshot, object type, and
  canonical identity. Display name, provider kind, array order, and free text
  MUST NOT establish identity.
- Candidate-set integrity, workflow, request, document, snapshot, and
  observation time MUST be validated before resolution.
- Changed or stale observations MUST invalidate prior decisions; no automatic
  reuse is allowed.
- A trusted design decision MUST originate from a deterministic trusted Host/UI
  event. Agent/model text, Tool arguments, provider guesses, Hardware IPC, and
  teaching evidence MUST NOT create it.
- Design disambiguation MUST NOT create physical confirmation,
  `TrustedOperationScope`, Tool/IPC authority, hardware execution, or EDA writes.
- A chosen Wire MAY use only the existing deterministic Wire-to-Net derivation.
  Multiple derived Nets MUST remain ambiguous.

## 5. Physical Confirmation

- EDA selection MUST NOT be treated as physical probe confirmation.
- `ProbeTarget` MUST mean only a design-side candidate target.
- Verified physical linkage MUST require trusted user/host confirmation outside
  the EDA selection and teaching-text surfaces.
- Physical confirmation MUST be scoped to channel, target,
  workflow/request correlation, and wiring state.
- Physical Policy MUST independently validate the physical confirmation's
  workflow identity against the trusted current workflow.
- Operation Scope workflow validation MUST NOT substitute for physical
  confirmation workflow validation, and the reverse MUST NOT substitute for
  Operation Scope validation.
- A wiring change MUST invalidate the previous physical confirmation.
- Missing trusted confirmation MUST NOT be replaced by
  `TeachingEvidenceContext` text, model prose, label equality, or inferred
  circuit context.

## 6. Evidence Categories

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

## 7. Deterministic Comparison

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

## 8. Design-to-Measurement Cross-Reference

- Cross-reference MUST be evaluated before authoritative comparison.
- A `VERIFIED_LINK` MUST require trusted evidence for the candidate
  `ProbeTarget`, physical confirmation, channel match, workflow/request match,
  design snapshot match, and temporal consistency.
- Label or name equality alone MUST NOT establish a verified link.
- Missing trusted linkage MUST gate comparison to a bounded indeterminate
  result.
- The evidence workflow MUST NOT create physical confirmation or
  `TrustedOperationScope`.

## 9. Grounding

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

## 10. Egress

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

## 11. Phase 8 Evidence Views

- `EngineeringEvidenceContext` MUST remain immutable and MUST NOT become a fact
  source, authorization object, or execution context.
- `TeachingDiagnosisContext` MUST remain an evidence-only projection. Its name
  MUST NOT be interpreted as proof that diagnosis exists.
- `TeachingDiagnosisContext` MUST NOT authorize or execute Tools.
- Current deterministic Phase 8 components MUST generate zero `INFERENCE`.
- `candidate_next_measurements` MUST remain empty/deferred until a later phase
  explicitly designs and reviews it.

## 12. Phase 8C Claim Sufficiency and Publication

- Phase 8C.1 SHA-256 context fingerprints, envelope IDs, subject identities,
  and comparison composite references MUST be interpreted as deterministic
  content identities only. They MUST NOT be used as authentication,
  authorization, trust, freshness, persistence, signature, or provenance proof.
- Trust MUST continue to derive from structured provenance, trusted
  Host/application boundaries, policy evaluation, and Grounding/Egress.
- A `ClaimPermission` with `ALLOW` is necessary but MUST NOT be sufficient for
  publication.
- Publication MUST additionally resolve the exact subject and support refs,
  preserve correct source attribution, semantically satisfy every mandatory
  `PublicationObligation`, reject forbidden strengthening, pass Grounding, and
  pass final Egress.
- Comparison interpretation MUST bind `ComparisonStatus` and the exact
  `ComparisonReason`. One `INDETERMINATE` reason MUST NOT be rendered as another.
- Only `INDETERMINATE / TOLERANCE_UNSPECIFIED` may support the corresponding
  missing-tolerance/compliance-undetermined statement. Other indeterminate
  reasons MUST preserve their actual reason and fail closed for that claim slot.
- Until separately reviewed knowledge/rule sources exist, educational
  knowledge, engineering inference, hypothesis, causal diagnosis, and next
  measurement proposals MUST remain blocked.
- Reasoning-policy objects MUST NOT create Tool execution authority,
  `TrustedOperationScope`, physical confirmation, IPC authorization, Hardware
  action, or provider/runtime secrets.
- Phase 8B.1 workflow ordering MUST remain: design/target validation ->
  cross-reference -> measurement evidence selection -> comparator -> assembler
  -> teaching projection.

## 12. Historical Validation Integrity

- Historical NOT PASS records MUST remain unchanged as historical evidence.
- A later fix or PASS MUST create a new validation record rather than rewriting
  a failed run.
- Lost measurements, discarded model output, unreported runtime outcomes, and
  unknown execution counts MUST NOT be reconstructed.
- A validation claim MUST remain bounded to the recorded device, workflow,
  environment, authority, and observations.

## 13. Phase 8B.3 Real Validation Boundary

- A JLCEDA snapshot in the current integration MUST mean observation identity
  only; it MUST NOT be claimed as proof of provider design immutability.
- Trusted design disambiguation MUST remain distinct from provider-observed
  primary selection and from trusted physical confirmation.
- A `VERIFIED_LINK` MUST NOT be interpreted as proof that the design remained
  immutable outside the bounded observation and coherence checks.
- Without explicit tolerance, Phase 8B.3 comparisons MUST remain
  `INDETERMINATE / TOLERANCE_UNSPECIFIED` and MUST NOT produce causal diagnosis.
- The Phase 8B.3 private request/receipt contract and its operation authority
  MUST remain validation-only; they MUST NOT be described as durable production
  authorization.
- Validation observer hooks MUST remain read-only. They MUST NOT grant
  authorization, mutate Scope or Physical Policy results, alter budgets or Tool
  arguments, or bypass IPC gates.

## 14. Change and Test Discipline

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
