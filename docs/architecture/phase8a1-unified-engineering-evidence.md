# Phase 8A.1 — Unified Engineering Evidence Architecture

Status: **PROPOSED — architecture review required**.

Scope: architecture and data-model design only. This proposal does not add an
Agent, diagnosis, hardware operation, EDA operation, tolerance, or physical
authorization.

## 1. Motivation

The project already represents three useful but separately owned bodies of
information:

- provider-neutral EDA document, selection, net, expectation, and candidate
  probe-target models;
- canonical Hardware measurement results and artifacts in the Python core;
- bounded `TeachingEvidenceContext` used by the governed Agent output path.

Phase 8 needs a context in which these bodies can be considered together
without erasing where each statement came from. The new
`EngineeringEvidenceContext` is therefore an immutable application read model,
not a replacement source of truth. It composes authoritative snapshots owned
by their existing subsystems and adds explicit links, deterministic comparison
records, limitations, and unresolved questions.

This solves four engineering problems:

1. it prevents a design target from being presented as a measurement;
2. it makes the physical link from a schematic node to an instrument channel
   auditable rather than inferred;
3. it gives deterministic comparison logic a provider-neutral input;
4. it gives future Teaching and Diagnosis Agents bounded structured context
   without granting them new execution authority.

## 2. Current reusable components

| Existing component | Authority retained | Reuse decision |
| --- | --- | --- |
| `DesignDocument`, `DesignObjectRef`, `DesignFingerprint` | observed design identity and finite snapshot/fingerprint scope | referenced directly; never copied into a JLCEDA-shaped model |
| `SelectionContext`, `CircuitNet`, `SignalExpectation` | selected design context and declared signal expectation | deterministically projected into design evidence and targets |
| `ProbeTarget` | candidate place suggested by the design | retained as a candidate only |
| Phase 7C `ProbeSetupConfirmation` / Physical Policy | trusted physical channel-to-target confirmation | remains the only physical confirmation authority |
| Python `MeasurementResult` | canonical measurement and analysis result | remains the Hardware-domain authority |
| `TeachingEvidenceContext` | bounded Agent-facing Hardware evidence semantics | embedded unchanged through a shared validated contract |
| `ArtifactReference` / opaque waveform evidence | reference and bounded metadata for large evidence | referenced; sample arrays never enter the unified context |
| TrustedOperationScope, Grounding, Egress, Runner Boundary | execution, claim, disclosure, and process safety | reused without weakening or duplication |

No JLCEDA runtime object, Harness SDK object, Driver, VISA resource, SCPI
command, or LLM object belongs in the new model.

## 3. Architectural position

`EngineeringEvidenceContext` belongs to the provider-neutral application
evidence layer. It is assembled after EDA and Hardware boundaries have each
produced their own validated domain/evidence objects. It does not sit inside
either adapter and does not become an execution port.

```text
EDA provider adapter                         Hardware path
        │                                         │
        ▼                                         ▼
provider-neutral EDA Domain              canonical MeasurementResult
        │                                         │
        │                              TeachingEvidenceContext projection
        │                                         │
        └──────────► EngineeringEvidenceAssembler ◄┘
                                  │
                                  ▼
                   EngineeringEvidenceContext
                    │             │             │
                    ▼             ▼             ▼
           deterministic     Teaching view   future guarded
             comparator       projection      Agent inference
```

The assembler may reject inconsistent inputs, but it cannot mutate a source
snapshot, authorize a Tool, confirm wiring, or invent missing evidence.

## 4. Unified context

The proposed immutable `EngineeringEvidenceContext` contains:

| Field | Meaning and invariant |
| --- | --- |
| `context_id` | unique identifier for this assembled evidence view; it is not a design snapshot or measurement session ID |
| `workflow_id` | trusted workflow correlation; must match confirmation and operation-scope context when those are present |
| `user_goal` | bounded user goal, treated as intent rather than evidence |
| `assembled_at` | timezone-aware assembly time |
| `design_context` | optional `DesignEvidenceContext`; absence stays explicit |
| `measurement_context` | optional validated `TeachingEvidenceContext`; its internal facts, analyses, quality, provenance, coherence, warnings, and limitations remain intact |
| `targets` | immutable `EngineeringTarget` values derived from explicit design or user evidence |
| `cross_references` | explicit, provenance-bearing relationships between design candidates, trusted confirmations, and measurements |
| `comparisons` | deterministic `ComparisonResult` values; never diagnoses |
| `provenance` | assembler name/version and identifiers of every input snapshot/context used |
| `coherence` | temporal and source relationship summary without claiming simultaneity |
| `limitations` | material bounded limitations inherited from all inputs plus assembly limitations |
| `unresolved_questions` | structured missing, ambiguous, stale, or conflicting information |
| `inferences` | empty in the deterministic core; reserved for later guarded Agent output, never populated by the assembler or comparator |

The context is a snapshot projection. Updating a design, confirmation, or
measurement creates a new context ID; an existing context is not patched in
place. This provides reproducibility and prevents evidence from different
times being silently blended.

### 4.1 Structural hierarchy

Evidence categories remain distinct both by type and by container:

| Category | Owner/container | Meaning |
| --- | --- | --- |
| `DESIGN_FACT` | `DesignEvidenceContext.evidence` | a statement actually present in a bounded design observation |
| `DESIGN_TARGET` | `EngineeringTarget` with source design evidence | an expected value or state, not an observation |
| `PHYSICAL_FACT` | `TeachingEvidenceContext.facts`, source `instrument` | a direct instrument observation |
| `SOFTWARE_ANALYSIS` | `TeachingEvidenceContext.analyses`, source `software_analysis` | a deterministic algorithm result |
| `SIMULATED_EVIDENCE` | any Hardware evidence item whose source is `simulated` | explicitly non-physical evidence |
| `INFERENCE` | future guarded inference collection | an interpretation; never created by deterministic comparison |

A consumer may create a display sequence across categories, but it must not
flatten them into an undifferentiated `facts` collection.

## 5. Design evidence model

### 5.1 `DesignEvidenceContext`

The design side contains the existing `DesignDocument`, the existing
`SelectionContext`, immutable `DesignEvidenceItem` records, and candidate
`ProbeTarget` values. All contained references must share provider, document,
and snapshot identity. A stale or ambiguous selection is represented as an
unresolved question; it is never repaired by guessing.

### 5.2 `DesignEvidenceItem`

| Field | Design |
| --- | --- |
| `evidence_id` | stable UUID within the assembled context |
| `kind` | component property, net identity, pin mapping, design-target declaration, design annotation, or selection-derived context |
| `label` | bounded human-readable semantic label |
| `value` | typed scalar/state value; no arbitrary object payload |
| `unit` | explicit unit when the value is quantitative; no implicit unit |
| `source_document` | existing `DesignDocument` reference including snapshot, optional native revision, and finite fingerprint scope |
| `source_object` | optional existing `DesignObjectRef`; required when the statement is object-specific |
| `origin` | document declaration, provider observation, user statement, or deterministic selection projection |
| `verification_state` | source-observed, user-asserted, ambiguous, stale, or unverified |
| `observed_at` | timezone-aware time the source was observed; optional only when truly unavailable |
| `native_revision` | provider-supplied value only; nullable and never synthesized |
| `derivation` | optional deterministic mapper name/version and input evidence IDs |

`source-observed` means the statement was observed in the design source. It
does not mean the physical circuit implements it correctly. No numeric
probability is invented for confidence. If a provider supplies a confidence
value in the future, it must retain provider provenance and cannot replace the
categorical verification state.

The current EDA fingerprint remains a finite-scope content fingerprint. It is
not promoted to an official project revision or proof of the whole design.

## 6. Engineering target model

`EngineeringTarget` is independent from measured evidence. It contains:

- `target_id`;
- semantic `metric` such as frequency, duty cycle, voltage, component value,
  or expected state;
- `expectation`, expressed as an exact value, inclusive range, or discrete
  state;
- explicit unit for a quantity;
- optional `ToleranceSpec`;
- `source_evidence_ids` pointing to the design/user declarations from which it
  was normalized;
- `target_source`: design or user;
- optional deterministic normalization provenance.

An `EngineeringTarget` cannot be created without at least one source evidence
reference. The source `DesignEvidenceItem` retains the literal declaration;
the target records the normalized, comparison-ready meaning and its derivation.
This avoids both silent interpretation and loss of the original design text.

### 6.1 Tolerance policy

Supported tolerance forms are limited to explicitly supplied:

- absolute tolerance with a compatible unit;
- relative tolerance with an explicit ratio/percent;
- an explicit inclusive expected range;
- exact equality for discrete state values.

Every tolerance records whether it came from the design or a trusted user
statement and references that source evidence. A comparator never supplies a
default tolerance. For an exact numeric target with no explicit tolerance, it
may calculate and report differences, but its status is `INDETERMINATE` with
reason `TOLERANCE_UNSPECIFIED`; even an apparently close value is not promoted
to MATCH.

Duty cycle uses the existing `DutyCycle` value object and its canonical ratio.
Presentation as percent is a deterministic conversion, not a new target.

## 7. Measurement evidence mapping

The unified context does not create a second Hardware evidence hierarchy.
`TeachingEvidenceContext` remains intact and is mapped only for categorization,
linking, comparison input selection, and presentation:

| Existing evidence source | Unified category | Rule |
| --- | --- | --- |
| `instrument` | `PHYSICAL_FACT` | preserve value, unit, method, timestamp, quality, warnings, artifact IDs, and instrument summary |
| `software_analysis` | `SOFTWARE_ANALYSIS` | preserve analysis algorithm, evidence artifact IDs, quality, and warnings |
| `simulated` | `SIMULATED_EVIDENCE` | always remain visibly simulated; never become physical evidence |
| existing inference item | `INFERENCE` | preserve as inference; never reclassify as fact or analysis |

Failed, unknown, degraded, and unavailable evidence remains in its original
state. Null values are not converted to zero. Material warnings, coherence,
required user action, and opaque artifact limitations are copied into the
unified limitations/coherence view while remaining present in the embedded
measurement context.

### 7.1 Cross-language ownership

Today `TeachingEvidenceContext` is defined in TypeScript inside the Harness
integration. A Python core model must not manually reproduce those fields.
Phase 8A.2 should first ratify the current structure, unchanged, as a
provider-neutral versioned JSON wire contract. TypeScript and Python bindings
must be generated or schema-validated from that one contract. JSON Schema is
the wire-format authority only; domain invariants remain in their owning
models.

The existing TypeScript `TeachingEvidenceContext` semantics are approved
behavior, but the TypeScript type itself is not the long-term cross-language
source of truth. A canonical, versioned JSON wire contract must become the
language-neutral source of truth; TypeScript and Python remain bindings to that
contract rather than independent protocol authorities.

This is a contract extraction, not a Hardware semantic redesign. If extraction
reveals an incompatible current producer, implementation stops for review.

## 8. ProbeTarget handoff

The handoff has three distinct records:

1. `ProbeTarget`: the design suggests that a node is a candidate measurement
   location;
2. trusted Phase 7C `ProbeSetupConfirmation`: a user confirms the real channel,
   target, grounding, voltage safety, time, and workflow scope;
3. measurement evidence: the Hardware path reports what that channel observed.

The assembler cannot create record 2 from record 1. Selecting `PWM_OUT`,
highlighting it, or resolving it to `U1.PA0` never means a probe is connected.
A missing confirmation produces a missing cross-reference and an unresolved
question, not an inferred connection.

## 9. Cross-reference semantics

`MeasurementDesignCrossReference` is an immutable relationship record rather
than a copied fact. It contains:

- `cross_reference_id`;
- candidate `probe_target_id` and design object reference;
- trusted `confirmation_id` and its workflow/correlation scope;
- measurement context/request identifier and channel;
- relationship status: `CONFIRMED`, `MISSING_CONFIRMATION`, `STALE_DESIGN`,
  `CHANNEL_MISMATCH`, `TARGET_MISMATCH`, or `AMBIGUOUS`;
- `established_at`;
- provenance references to all three source records;
- temporal qualification and limitations.

`CONFIRMED` requires all of the following:

- confirmation came from the trusted Phase 7C host/policy path;
- workflow/correlation scope matches the assembled workflow;
- confirmation target matches the candidate ProbeTarget;
- confirmed channel matches the measurement request/provenance channel;
- the design snapshot and target referenced by the confirmation match the
  design context;
- the measurement occurred after confirmation;
- no recorded wiring change invalidated confirmation.

Only a `CONFIRMED` link permits the teaching projection to say that a channel
measurement corresponds to `PWM_OUT`. Without it, the valid statement is only
that the instrument observed a value on a channel.

## 10. Deterministic comparison boundary

`EngineeringComparator` is a provider-neutral application port/domain service.
It accepts one `EngineeringTarget` and one eligible physical, software, or
simulated evidence locator. It has no LLM, Agent, EDA adapter, Harness, Driver,
VISA, or SCPI dependency.

`ComparisonResult` contains:

- `comparison_id`;
- metric;
- target ID and observed evidence locator;
- expected and observed typed values with units;
- absolute difference when defined;
- relative difference when defined and the expected reference is non-zero;
- status: `MATCH`, `MISMATCH`, or `INDETERMINATE`;
- bounded reason code;
- comparator name/version and unit-conversion provenance;
- source category retained for the observation;
- limitations.

Deterministic reason codes include:

| Condition | Status/reason |
| --- | --- |
| explicit compatible tolerance/range and observed value inside | `MATCH / WITHIN_EXPLICIT_TOLERANCE` |
| explicit compatible tolerance/range and observed value outside | `MISMATCH / OUTSIDE_EXPLICIT_TOLERANCE` |
| numeric target lacks tolerance | `INDETERMINATE / TOLERANCE_UNSPECIFIED` |
| target or observation missing/unavailable | `INDETERMINATE / EVIDENCE_MISSING` |
| units incompatible or conversion not allowlisted | `INDETERMINATE / UNIT_INCOMPATIBLE` |
| design snapshot/cross-reference stale or ambiguous | `INDETERMINATE / CONTEXT_UNRESOLVED` |
| discrete expected state exactly equals/does not equal observed state | `MATCH` or `MISMATCH / EXACT_STATE_COMPARISON` |

The comparator may report that evidence disagrees with a target. It cannot
claim that an MCU timer, oscillator, probe, firmware configuration, or circuit
component caused the difference. `ComparisonResult` is not diagnosis.

### 10.1 Evidence locators

Current `TeachingEvidenceContext.EvidenceItem` has no stable evidence ID.
Changing the frozen Hardware semantics merely to add one is unnecessary. The
assembler creates an external immutable locator containing the measurement
context ID, original collection (`facts`, `analyses`, or `inferences`), item
ordinal, label, and bounded provenance digest. This locates an item without
mutating or copying its authority.

## 11. Temporal, provenance, and coherence semantics

The unified context records four independent clocks/identities:

- EDA `captured_at`, `snapshot_id`, nullable provider `native_revision`, and
  finite `content_fingerprint` scope;
- physical confirmation time and workflow scope;
- measurement start/completion or observation time and session/request ID;
- context assembly time.

No equality between these timestamps is assumed. Cross-source coherence uses
explicit values such as same artifact, sequential same session, version
guarded, stale, or unknown. It never introduces `simultaneous` or `atomic`
without source evidence.

`EngineeringContextProvenance` records the assembler implementation/version,
input design snapshot, measurement context identity, confirmation identity,
target source evidence, comparator version, and applied unit conversions. It
does not record adapter runtime objects or secrets.

## 12. Missing and conflicting evidence

Missing information is represented structurally:

- absent design context or target remains `None`/empty;
- unavailable Hardware observations retain null value and unavailable quality;
- missing confirmation produces no confirmed cross-reference;
- ambiguous EDA selection remains ambiguous;
- absent analysis does not become an instrument fact;
- no default target, tolerance, quality, or timestamp is synthesized.

`UnresolvedQuestion` contains a bounded code, subject reference, explanation,
and optional safe next-evidence suggestion. Initial codes cover missing target,
missing measurement, unavailable analysis, unavailable instrument observation,
missing physical confirmation, ambiguous selection, stale design, incompatible
unit, unspecified tolerance, and conflicting evidence.

Contradictions remain visible as separate evidence and comparison records. For
example, a 10 kHz target, 8 kHz instrument fact, and 8.02 kHz software analysis
remain three records with separate provenance. With explicit tolerance, two
target comparisons may be MISMATCH; without it they remain INDETERMINATE while
showing their differences. Neither form asserts a root cause.

## 13. Teaching projection

`TeachingDiagnosisContext` is a deterministic bounded projection of
`EngineeringEvidenceContext`, not natural-language output. It groups:

- what the design source says;
- what the instrument observed;
- what software analysis derived;
- deterministic MATCH/MISMATCH/INDETERMINATE comparisons;
- conflicts and remaining unknowns;
- safe candidate questions or measurements that could reduce uncertainty.

A suggested next measurement is only a semantic candidate. Executing it later
still requires a new/current TrustedOperationScope and, for real hardware, a
valid Physical Policy decision. The projection contains no invented inference
and grants no Tool authority. Any later model prose still traverses Grounding
and Egress.

## 14. PWM_OUT design example

The example assembles the following without flattening:

| Layer | Evidence |
| --- | --- |
| Design fact | selected net identity `PWM_OUT`; source endpoint `U1.PA0` |
| Design targets | frequency 10 kHz; duty cycle 30%; source is design expectation |
| Probe candidate | design suggests `PWM_OUT` as a ProbeTarget |
| Physical confirmation | trusted confirmation links CH1 to `PWM_OUT` |
| Physical facts | instrument frequency approximately 10.02 kHz; instrument Vpp approximately 0.4 V |
| Software analysis | frequency approximately 10.01 kHz; duty approximately 29.95% |
| Comparison | differences can be computed; MATCH/MISMATCH requires explicit tolerance |
| Inference | none from the deterministic core |

The word “approximately” in this design example summarizes observed display
values; it is not a comparison tolerance. If neither the design nor user
provides tolerance, both numeric comparison statuses are INDETERMINATE.

## 15. Dependency and safety boundaries

Required dependency direction:

```text
provider-neutral evidence models
        ▲
        │
comparison + assembly services
        ▲
        │
JLCEDA mapper / Hardware evidence contract adapters / Agent projection
```

Forbidden dependencies and authority transfers:

- engineering evidence models must not import JLCEDA, Harness, LLM, Driver,
  VISA, SCPI, or WebSocket modules;
- comparison must not call a model or adapter;
- EDA selection and ProbeTarget must not create physical confirmation;
- Hardware observation source classifications must not be rewritten;
- design targets must not enter physical facts;
- software analysis must not enter instrument facts;
- the unified context must not issue or enlarge TrustedOperationScope;
- no comparison or teaching projection may weaken Physical Policy, Grounding,
  Egress, or Runner Failure Boundary.

## 16. Proposed architecture tests

Phase 8A.2 should begin with failing tests for:

1. DesignEvidence has no JLCEDA adapter dependency.
2. EngineeringEvidenceContext has no Harness or LLM dependency.
3. Comparator has no LLM, Driver, VISA, SCPI, EDA adapter, or transport
   dependency.
4. A design target cannot be inserted into physical facts.
5. Software analysis cannot be reclassified as an instrument fact.
6. Simulated evidence remains simulated after assembly and comparison.
7. EDA selection or highlight cannot construct physical confirmation.
8. A confirmed cross-reference requires matching workflow, target, snapshot,
   channel, timestamp order, and unchanged wiring.
9. Missing evidence remains missing and produces no zero/default value.
10. Numeric comparison without explicit tolerance is INDETERMINATE.
11. Incompatible units are INDETERMINATE rather than guessed.
12. Comparison records preserve target and observation provenance.
13. Conflicting design, instrument, and software values remain distinct.
14. Opaque artifacts expose metadata/reference only, never samples.
15. Design snapshot, confirmation, and measurement are not labelled
    simultaneous.
16. Teaching projection cannot execute a suggested next measurement.
17. Shared TypeScript and Python contract fixtures accept/reject identically.
18. Existing Phase 7C safety, EDA, Hardware, and architecture suites remain
    unchanged and green.

## 17. Phase 8A.2 implementation proposal

Only after this review is approved, the smallest implementation slice should
be:

```text
protocols/engineering-evidence/v1/
  teaching-evidence-context.schema.json
  fixtures/

src/ai_instrument_assistant/domain/engineering_evidence/
  __init__.py
  models.py

src/ai_instrument_assistant/application/ports/
  engineering_comparator.py

src/ai_instrument_assistant/application/services/
  engineering_evidence_assembler.py
  engineering_comparison.py

src/ai_instrument_assistant/integrations/deepseek_harness/
  teaching_evidence_contract.py

tests/architecture/
  test_engineering_evidence_boundaries.py

tests/unit/domain/engineering_evidence/
  test_models.py

tests/unit/application/services/
  test_engineering_evidence_assembler.py
  test_engineering_comparison.py

tests/contract/engineering_evidence/
  test_shared_contract.py

extensions/deepseek-harness/tests/contract/
  engineering-evidence-contract.test.ts
```

Recommended sequence:

1. freeze current `TeachingEvidenceContext` wire shape with shared valid and
   invalid fixtures, without changing its semantics;
2. implement immutable design evidence, target, locator, cross-reference,
   comparison, provenance, coherence, and unresolved-question value objects;
3. implement the assembler with no comparator and prove strict separation;
4. implement explicit-tolerance comparison only;
5. implement the bounded `TeachingDiagnosisContext` projection;
6. run all prior architecture and safety suites before discussing a Diagnosis
   Agent.

No Agent inference, real model call, hardware access, EDA API extension, or
automatic next measurement belongs in Phase 8A.2.

## 18. Compatibility findings and review gates

1. Existing EDA models already separate design snapshot identity,
   fingerprint scope, ProbeTarget, and connection confirmation sufficiently;
   no JLCEDA or EDA-core semantic change is required.
2. Existing Python MeasurementResult and TypeScript TeachingEvidenceContext
   already preserve instrument/software/simulated source and coherence; no
   Hardware canonical semantic change is required.
3. The only material boundary gap is cross-language ownership of
   `TeachingEvidenceContext`. A shared versioned wire contract is required to
   avoid independently evolving Python and TypeScript copies.
4. The current Teaching evidence item has no stable item ID. An external
   evidence locator avoids changing the frozen model.
5. Phase 7C Physical Policy uses the trusted confirmation as authority; the
   unified context can reference its result but cannot manufacture it.
6. Current design signal expectations do not carry tolerance provenance.
   Comparisons therefore remain INDETERMINATE until an explicit design/user
   tolerance is supplied.
7. No stop condition is currently triggered: the proposal needs no design
   target promotion, JLCEDA leakage, LLM comparator, inferred confirmation,
   arbitrary tolerance, or weakened Phase 7C boundary.

Implementation must stop for a new architecture review if the shared evidence
contract cannot represent current `TeachingEvidenceContext` without changing
meaning, or if a use case requires any forbidden authority transfer above.
