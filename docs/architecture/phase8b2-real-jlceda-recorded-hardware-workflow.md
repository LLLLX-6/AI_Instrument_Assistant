# Phase 8B.2 — Real JLCEDA Design Context with Recorded Hardware Evidence

Status: **COMPLETE — REAL JLCEDA PLUS RECORDED HARDWARE EVIDENCE PASS**.
The provider selection limitation remains valid and is recorded in
[`ADR 0005`](../adr/0005-jlceda-real-selection-role-semantics.md).

## 1. Purpose

Phase 8B.2 validates one new external boundary only: real, read-only JLCEDA
design context. It composes that design-side evidence with canonical recorded
hardware evidence through the existing deterministic
`EngineeringEvidenceWorkflow`. It does not authorize live hardware or a model.

## 2. Real JLCEDA Boundary

The approved path is unchanged:

```text
official JLCEDA read-only APIs
  -> bounded TypeScript transport DTO
  -> authenticated aia-jlceda/v1 localhost protocol
  -> Python JLCEDARemoteAdapter / JLCEDADomainMapper
  -> provider-neutral EDAInterface models
```

The validation runner requests exactly one active document and one selection.
It performs no highlight and no EDA write. Connection, authentication, active
document, selection, projection, and workflow failures are reported as bounded
stage/code pairs. A real-read failure cannot fall back to fixture design data.

## 3. Provider-Neutral Projection

`EDADesignEvidenceCaptureService` depends only on `EDAInterface`. It projects a
bounded document fact and, when supported by the observed selection context, a
selected-net connectivity fact and design-only `ProbeTarget`.

The existing JLCEDA document and selection operations use separate AIA
observation tokens. When their canonical document identity matches but their
tokens differ, the projection uses the selection observation token for the
composed design context and clears revision, fingerprint, and dirty-state data
that cannot truthfully be inherited across observations. This is recorded as a
non-atomic observation limitation. An identity mismatch fails instead of being
silently reconciled.

No official JLCEDA object, SDK type, transport DTO, or primitive object enters
the domain or evidence workflow.

## 4. Design Provenance

JLCEDA-observed document and net structure are `DESIGN_FACT` evidence with
`DESIGN_DERIVED / SNAPSHOT_BOUNDED` provenance. The projector does not consume
or invent signal frequency, duty cycle, tolerance, or measurement values.

The validation's 10 kHz frequency and 30 percent duty-cycle expectations are
separate target declarations with `USER_STATEMENT / USER_ASSERTED` evidence and
`USER_PROVIDED` target provenance.

**Real JLCEDA supplied structural design evidence. Expected electrical targets
in this validation were supplied as trusted user context and were not claimed
as schematic-derived values.**

## 5. ProbeTarget Semantics

A single provider-observed net, or a single selected wire with one
provider-observed contextual net, can produce a deterministic design-only
`ProbeTarget`. Its identity is derived from provider, canonical object
reference, and selection snapshot. It has no physical location and is not a
physical connection confirmation.

Empty, unsupported, multi-object, or multi-net ambiguous selections create no
probe target. Display-name equality is never used to prove a physical link.

## 6. Recorded Hardware Fixture

The hardware input is the schema-validated canonical Evidence v1 PWM fixture
at `protocols/evidence/v1/fixtures/valid/pwm-teaching-context.case.json`. It
contains recorded instrument frequency, recorded software frequency and duty,
quality, warnings, sequential coherence, and an opaque artifact reference. No
sample array is loaded or exposed.

The pure Evidence v1 binding now resides under the provider-neutral `protocol`
package. Its previous Harness integration path remains a compatibility import;
there is still one implementation and one Schema authority.

## 7. Trusted Confirmation Fixture

The physical-link input is an immutable, non-executing validation fixture with:

- `TRUSTED_USER_EVENT` source;
- matching workflow and request correlation;
- CH1 and exact canonical target reference;
- the current projected design snapshot and probe-target identifier;
- low-voltage, common-ground, and unchanged-wiring confirmations;
- confirmation time before the recorded measurement time.

It represents the shape of trusted Phase 7C host evidence for deterministic
linkage. It is not a real physical event, cannot authorize execution, and is
not created from JLCEDA selection.

## 8. Cross-Reference

The existing Phase 8B.1 cross-reference runs before comparison. A verified
link requires probe, confirmation, exact target and probe identifiers,
workflow, request, channel, snapshot, trusted source, and temporal ordering.
Snapshot, target-reference, channel, workflow, request, and name-only mismatch
cases remain unverified and gate all comparisons.

## 9. Workflow Execution

The validation reuses the existing order:

```text
design/target validation
  -> cross-reference
  -> recorded measurement selection
  -> comparator
  -> assembler
  -> TeachingDiagnosisContext projection
```

It does not duplicate cross-reference, metric selection, unit conversion,
tolerance, assembly, or teaching projection logic.

## 10. Comparator Results

Automated contract-style validation proves the expected deterministic behavior:

- 10 kHz vs recorded instrument 10020 Hz: `INDETERMINATE /
  TOLERANCE_UNSPECIFIED`;
- 10 kHz vs recorded software 10010 Hz: `INDETERMINATE /
  TOLERANCE_UNSPECIFIED`;
- 30 percent vs recorded software ratio 0.2995: `INDETERMINATE /
  TOLERANCE_UNSPECIFIED`;
- an explicit user-provided ±1 percent frequency tolerance produces separate
  `MATCH` results for the two recorded frequency sources.

No result is a causal diagnosis, and instrument/software evidence remains
separate.

## 11. Missing and Negative Scenarios

Automated tests cover empty selection, unsupported object, ambiguous
selection, document identity change, provider failure without fallback,
snapshot mismatch, exact target-reference mismatch, channel mismatch, workflow
mismatch, request mismatch, name-only equality, missing design target, and
missing recorded measurement. Missing values remain missing; no comparison,
target, or probe is fabricated.

## 12. No-Hardware Proof

The new projection and validation runner import no instrument driver,
`MeasurementService`, hardware runtime, VISA, or SCPI implementation. The
validation summary fixes hardware-backend starts, IPC dispatches, physical
measurements, and EDA writes at zero. Hardware input is recorded only.

## 13. No-Model Proof

The runner imports no model runtime or Agent loop, requires no model credential,
and makes zero model requests. Both final evidence contexts require empty
inferences, and candidate next measurements remain empty.

## 14. Architecture Boundaries

- the evidence workflow remains provider-neutral;
- domain models import no JLCEDA SDK, protocol, or runtime;
- JLCEDA normalization remains in the existing integration adapter;
- the application projector depends on `EDAInterface`, not JLCEDA;
- selection creates neither physical confirmation nor operation scope;
- real design evidence still passes the Phase 8B.1 cross-reference gate;
- Evidence v1 Schema remains the recorded-evidence wire authority.

## 15. Real Validation Attempts

### Attempt 1 — NOT PASS

- Date: 2026-09-10;
- stage: `connection`;
- code: `extension_not_authenticated`;
- active document: not observed;
- selection: not observed;
- fixture fallback: zero;
- automatic retry: zero;
- EDA writes: zero;
- hardware execution: zero;
- model requests: zero.

No document, selected object, snapshot, or provider result is reconstructed for
this attempt. A later successful manual validation must be recorded as a new
attempt, not by rewriting Attempt 1.

### User-reported intervening attempts — NOT PASS

After authentication was established, repeated user-run validation attempts
reached `projection / ambiguous_selection`. Their exact count and selection
payloads were not reconstructed. They remain historical failures rather than
being merged into the bounded diagnostic attempt below.

### Bounded diagnostic attempt — NOT PASS

- Date: 2026-09-10;
- authentication: succeeded;
- provider-selected object count: two;
- provider kinds: `Wire`, `Component`;
- selected wire display name: `PWM_OUT`;
- component display name: unavailable;
- safely derived net count: one;
- projected probe-candidate count: one;
- projected candidate kind: `NET`;
- ambiguity reason: `multiple_selected_objects`;
- resolution stage: `selection_cardinality`;
- observed semantic expansion: `wire_to_net`;
- fixture fallback, automatic retry, EDA write, hardware execution, and model
  request: zero.

Only bounded identities were emitted during the live diagnostic. Repository
test evidence retains synthetic identifiers and the real structural shape; it
does not retain the live document or primitive identifiers. The approved
selection contract exposed no primary object or parent relationship proving
that the extra Component could be ignored or treated as belonging to the Wire.

This result proves that Wire-to-Net expansion is not the source of ambiguity:
one derived Net candidate was available. The fail-closed result occurs earlier
because the provider reported two selected objects. Phase 5 permits a selected
Wire and a separately derived Net, but it does not permit silently dropping an
additional provider-selected Component. Therefore no projection behavior is
relaxed in this diagnostic task.

### Phase 8B.2A trusted-disambiguation validation attempt — NOT PASS

- Date: 2026-09-11;
- gateway: started on the configured localhost port;
- stage: `connection`;
- code: `extension_not_authenticated`;
- authenticated JLCEDA session: not observed within the bounded window;
- document reads: zero;
- selection reads: zero;
- trusted design decision: not created;
- fixture fallback and automatic retry: zero;
- EDA writes, hardware execution, and model requests: zero.

The trusted-disambiguation implementation and automated tests passed before
this attempt, but the real Wire + Component selection was not observed because
authentication did not complete. This attempt remains NOT PASS and does not
replace the earlier provider diagnostic. A future separately authorized retry
must be recorded as a new validation attempt.

### Trusted-disambiguation revalidation — PASS

- Date: 2026-09-11;
- real authenticated JLCEDA: yes;
- active schematic and selection reads: one each;
- provider observation: Wire plus Component, retained unchanged;
- provider primary object: null;
- trusted choice: exact bounded candidate `A`, recorded separately as the Wire;
- candidate binding: current set fingerprint, workflow, request, document,
  snapshot, and observation time validated;
- derivation: chosen Wire to exactly one Net to design-only ProbeTarget;
- original Component provenance: preserved;
- physical confirmation: trusted non-executing fixture;
- Hardware evidence: canonical recorded fixture;
- deterministic workflow and both evidence contexts: completed;
- engineering/teaching inferences and next measurements: zero;
- real hardware, Hardware backend/runtime/service, model, AgentLoop, EDA writes,
  automatic retry, and design-fixture fallback: zero.

The bounded PASS and exact `A` choice were reported by the user after the run.
The repository intentionally does not retain the raw output or unnecessary real
provider/document/object/snapshot identifiers. The PASS path's deterministic
guards establish the listed workflow conditions without reconstructing those
identifiers.

The 10 kHz and 30 percent values were not relabeled as schematic facts. They
remain `USER_PROVIDED DESIGN_TARGET`. Recorded instrument observations remain
`PHYSICAL_FACT`, recorded software results remain `SOFTWARE_ANALYSIS`, and
without explicit tolerance the comparison remains
`INDETERMINATE / TOLERANCE_UNSPECIFIED`. Only the separate explicit one-percent
tolerance fixture produces `MATCH`. No diagnosis or causal inference was
generated.

This PASS does not supersede or rewrite any earlier NOT PASS attempt. It also
does not invalidate ADR 0005: JLCEDA still supplied no documented primary
selection evidence. Resolution came from the separate trusted user decision.

## 16. Limitations and Phase 8B.3

Phase 8B.2 does not prove a live combined EDA-and-instrument observation. Its
hardware evidence and physical confirmation are recorded/test fixtures, and
the design and hardware observations are neither simultaneous nor atomic.
JLCEDA connectivity endpoints and signal expectations remain missing when the
approved provider API does not supply them. No highlight rendering, mutation,
diagnosis, source preference, tolerance policy, or next-measurement planning is
claimed.

Phase 8B.3 is now the current design phase for a real JLCEDA plus real
DS1102Z-E validation. It must separately review physical authorization,
temporal/coherence semantics, and the exact bounded workflow. Phase 8B.2 grants
no such authority.
