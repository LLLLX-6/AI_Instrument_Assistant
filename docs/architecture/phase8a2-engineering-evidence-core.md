# Phase 8A.2 — Shared Engineering Evidence Contract and Immutable Core

Status: implemented for architecture review; not yet committed.

## Decision

Phase 8A.2 introduces deterministic infrastructure that composes existing EDA
evidence, the approved `TeachingEvidenceContext`, explicit engineering targets,
trusted physical-link evidence, and comparison results. The resulting
`EngineeringEvidenceContext` is an immutable read model. It is not an evidence
source and does not replace any canonical design, measurement, artifact, or
Phase 7C safety authority.

The six categories are structurally separate:

- `DESIGN_FACT`
- `DESIGN_TARGET`
- `PHYSICAL_FACT`
- `SOFTWARE_ANALYSIS`
- `SIMULATED_EVIDENCE`
- `INFERENCE`

The deterministic Phase 8A.2 assembler always emits an empty `INFERENCE`
collection.

## Canonical cross-language contract

`protocols/evidence/v1/` is the language-neutral wire-format authority.
`TeachingEvidenceContext`, `EvidenceItem`, and the exchange view of
`EngineeringEvidenceContext` have closed Draft 2020-12 JSON Schemas. Python and
TypeScript implementations are validation and semantic bindings, not competing
wire authorities.

The approved Phase 7C `TeachingEvidenceContext` behavior remains unchanged:
FACT/ANALYSIS/source meaning, quality, warnings, provenance, coherence,
unavailable observations, execution/failure fields, and artifact opacity are
preserved. The TypeScript runtime's flattened artifact fields are adapted to a
canonical nested `reference` field so the existing Hardware v1
`ArtifactReference` schema can be reused by `$ref`. Null optional reference
metadata is omitted on the wire and restored as null by the TypeScript binding.
This is a representation binding, not an evidence-semantic change.

JSON Schema controls wire shape. A ratio/percent pair also has a semantic
invariant (`percent == ratio * 100`) that Draft 2020-12 cannot express for an
arbitrary continuous number. Both language bindings enforce the same invariant;
the canonical ratio remains the internal domain representation.

Within v1, existing required fields and meanings cannot be changed silently.
Optional compatible extensions require documented, deliberate support in both
bindings. A rename, removal, new required field, enum narrowing, or semantic
change requires a new schema version.

## Immutable models

`DesignEvidenceItem` retains its evidence identifier, kind, bounded value, unit,
document snapshot, optional object reference, verification state, observation
time, origin, native revision, and finite fingerprint scope. Category is derived
from the kind; callers cannot relabel a design target as a physical fact.

`EngineeringTarget` supports exactly three expectation forms:

1. exact numeric quantity;
2. explicit inclusive numeric range;
3. discrete state.

Target provenance is either design-derived or explicitly user-provided and must
reference source design-target evidence. Exact numeric targets may carry an
explicit absolute or relative tolerance. Ranges are already explicit bounds and
cannot carry a second tolerance. No default tolerance exists.

Existing provider-neutral `DesignDocument`, `DesignObjectRef`, `ProbeTarget`,
`SelectionContext`, `ArtifactReference`, and `DutyCycle` are reused. No provider,
native EDA object, instrument driver, or transport type enters the core.

## Measurement mapping

The binding maps only the existing teaching evidence:

- instrument FACT → `PHYSICAL_FACT`;
- software analysis → `SOFTWARE_ANALYSIS`;
- any simulated source → `SIMULATED_EVIDENCE`;
- explicit inference → `INFERENCE`.

Values, units, quality, warnings, timestamps, methods, algorithm metadata,
artifact identifiers, coherence, limitations, and failure state remain intact.
Unavailable remains null/unavailable. The waveform is an opaque
`ArtifactReference` plus bounded metadata; sample arrays are forbidden.

Because the frozen teaching items do not have stable evidence IDs, a bounded
external `MeasurementEvidenceLocator` identifies context, collection, ordinal,
label, metric, and category without mutating the approved context.

## Cross-reference boundary

`ProbeTarget` is only a design-side candidate. It cannot establish physical
connection. `TrustedPhysicalConfirmationEvidence` is a read-only reference to
already-authoritative Phase 7C host state and explicitly has no execution or
authorization role.

A `VERIFIED_LINK` requires all of the following to match:

- trusted user-event origin;
- workflow and request-correlation scope;
- channel;
- probe target identifier and canonical target reference;
- design snapshot;
- confirmation before or at measurement time;
- the preserved low-voltage, common-ground, and unchanged-wiring confirmations.

The result preserves confirmation time, measurement time, workflow/request
scope, channel, snapshot, and reference identifiers. Label equality is never a
linking rule. Missing confirmation yields `INSUFFICIENT_EVIDENCE`; inconsistent
facts yield `MISMATCH`. The model also reserves `UNVERIFIED_LINK` for upstream
states that are explicitly known but not authoritative.

Design capture time, target evidence time, physical confirmation time,
measurement observation time, and assembly time remain separate. No field
claims atomic acquisition. Existing `sequential_same_session` coherence is
preserved verbatim.

## Deterministic assembler

The assembler validates source references, snapshot/workflow/context
consistency, and comparison references. It composes supplied evidence without
inventing targets, tolerances, measurements, confirmations, or diagnoses.
Missing design, target, measurement, or physical-link evidence is recorded as a
bounded unresolved question. Multiple selected objects without a primary object
are recorded as `AMBIGUOUS_DESIGN_SELECTION`.

## Deterministic comparator

The comparator is a provider-neutral application port with one deterministic
implementation. It supports a closed conversion allowlist:

- Hz ↔ kHz;
- V ↔ mV;
- s ↔ ms ↔ us/µs;
- ratio ↔ percent/% when the metric is explicitly duty cycle.

For an exact numeric target without explicit tolerance, the difference and
relative difference are calculated when possible, but the result is always
`INDETERMINATE / TOLERANCE_UNSPECIFIED`. Only explicit absolute tolerance,
relative tolerance, or range bounds can produce MATCH/MISMATCH. Incompatible
metric/unit, missing/unavailable evidence, and unverified physical links fail
closed to bounded INDETERMINATE reason codes.

Each source is compared separately; instrument and software observations are
never averaged. A `ComparisonResult` records comparator name/version and emits no
causal explanation or diagnosis.

## Teaching projection and safety boundary

`TeachingDiagnosisContext` is a deterministic structured projection grouped by
design facts, targets, physical observations, software analyses, simulation,
comparisons, quality, warnings, coherence, limitations, and unresolved
questions. It generates no prose diagnosis and no inference.

Candidate next measurements are structurally recommendations only. Phase 8A.2
generates none. The model carries no `TrustedOperationScope`, physical-policy
confirmation creator, Tool request, or execution method. A future consumer must
still pass every Phase 7C operation-scope, physical-policy, grounding, egress,
and runner boundary.

## Tests and limitations

Shared valid/invalid fixtures are consumed by Python and TypeScript. Both
bindings round-trip the canonical PWM fixture, which establishes transitive
TS→JSON→Python and Python→JSON→TS semantic equality. Tests reject source-kind
confusion, unavailable values with fabricated data, unknown fields, and raw
waveform samples. Architecture tests prevent core dependencies on concrete EDA,
instrument, transport, Harness, model, or measurement-service implementations.

Current bounded limitations:

- The exchange schema is available for cross-language validation, while the
  Phase 8A.2 typed engineering assembler remains Python-side; no remote transport
  is introduced.
- The deterministic metric locator recognizes only an explicit allowlist of
  approved teaching labels. Unknown labels become metric `OTHER` and cannot be
  compared authoritatively.
- The frozen `TeachingEvidenceContext` does not itself carry measurement channel,
  workflow, request correlation, or a context UUID. Those facts remain in the
  separate trusted cross-reference record and outer composed context rather than
  being silently added to the frozen model.
- Cross-reference evidence is process input from an already trusted Phase 7C
  host boundary. Durable issuance, storage, or recovery is outside Phase 8A.2.
- No diagnosis, causal reasoning, artifact fetching, automatic planning, model
  call, EDA mutation, or physical execution exists in this phase.
