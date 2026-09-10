# Phase 8B.2A — Trusted Design Selection Disambiguation

Status: **COMPLETE — REAL VALIDATION PASS**

This implementation follows the accepted Option D finding in
[`ADR 0005`](../adr/0005-jlceda-real-selection-role-semantics.md). It designs
an application-level trusted-user decision for one provider-observed ambiguous
selection without changing provider truth.

## 1. Problem and invariant

The real JLCEDA observation was:

```text
provider selection: Wire(PWM_OUT) + Component(name unavailable)
provider primary:   null
derived context:    one Net(PWM_OUT)
```

The provider exposes no documented primary, role, ordering, or ownership
evidence. The frozen provider rule therefore remains:

```text
Wire + Component + no provider role evidence -> ambiguous_selection
```

The proposed resolution makes a different and narrower claim:

```text
JLCEDA observed both objects.
A trusted user selected the already-observed Wire for this workflow/request.
```

It never claims that JLCEDA identified the Wire as primary.

## 2. Boundary and trust flow

```text
JLCEDA read-only observation
  -> unchanged SelectionContext(primary_object = null)
  -> bounded ambiguity diagnostic
  -> trusted Host/UI renders exact observed candidates
  -> deterministic user event selects an opaque candidate identity
  -> application decision issuer records trusted decision
  -> fail-closed decision validator
  -> chosen Wire
  -> existing deterministic Wire-to-Net expansion
  -> ProbeTarget + separate derivation/audit record
```

The trusted authority is the Host/Application composition boundary. The
decision may be issued only from a deterministic UI event already bound to the
displayed candidate set. Free text is not a decision. Agent text, Tool
arguments/results, DeepSeek output, provider guesses, Hardware IPC, and
`TeachingEvidenceContext` are untrusted for this purpose.

For the bounded Phase 8B.2 revalidation, the trusted UI may be a local CLI menu
owned by the Python validation host. An index such as `A` is resolved locally
against the exact rendered challenge and immediately converted to an opaque
candidate identity. The stored decision never relies on the label or index.

## 3. Proposed application models

These are provider-neutral immutable application/workflow objects. They do not
belong in the EDA provider Domain observation and do not redefine
`DesignSelection`.

### 3.1 `DesignSelectionCandidateIdentity`

An equality value derived from an existing `DesignObjectRef`:

- `provider`
- `document_id`
- `snapshot_id`
- `object_type`
- `canonical_id`

`display_name`, `provider_kind`, and `native_id` are excluded from identity.
They remain bounded presentation/provenance metadata on the original
`DesignObjectRef`; they cannot select an object. `canonical_id` is the existing
adapter-produced identity, while provider/document/snapshot/type prevent reuse
outside its exact observation scope.

### 3.2 `DesignSelectionCandidateSetBinding`

- `document_ref`: the selection's document `DesignObjectRef`, including the
  selection observation `snapshot_id`;
- `selection_observed_at`: timezone-aware host capture time;
- `presented_candidates`: the exact provider-observed
  `DesignSelection.selected_objects`, preserved for audit and UI rendering;
- `candidate_set_fingerprint`: deterministic, order-independent digest of the
  document identity and candidate identities;
- `fingerprint_scope`: fixed value
  `design-selection-candidate-identities/v1`.

The binding requires at least two unique candidates because it represents an
ambiguity challenge. Every candidate must belong to the same provider,
document, and snapshot as `document_ref`.

### 3.3 `TrustedDesignSelectionDecision`

- `decision_id`: UUID identifying the trusted user event record;
- `workflow_id`: exact trusted Host/Application workflow identifier;
- `request_correlation_id`: exact trusted request identifier;
- `candidate_binding`: the complete binding above, including all choices that
  were presented;
- `selected_object`: the exact `DesignObjectRef` selected from
  `presented_candidates`;
- `trusted_origin`: closed enum containing only
  `TRUSTED_HOST_USER_EVENT` in this phase;
- `decided_at`: timezone-aware time at which the bound UI event was accepted.

No separate `design_document` field is needed because the binding carries the
selection document identity and snapshot. No free-form rationale is included;
it would not add authority and could accidentally become an inference surface.
The constructor/factory must require `selected_object` to equal one presented
candidate, not merely share a display name.

### 3.4 `TrustedDesignSelectionResolution`

A structured application result, not a replacement provider selection:

- `status`: `RESOLVED`, `DECISION_REQUIRED`, `INVALID_DECISION`,
  `UNSUPPORTED_CHOICE`, or `DERIVED_TARGET_AMBIGUOUS`;
- `reason_codes`: finite, deterministic reason codes;
- `provider_selection`: the complete original `SelectionContext`;
- `decision`: the validated decision when one was supplied;
- `chosen_source_object`: the selected provider-observed object when valid;
- `derived_target_object`: the exact derived Net when uniquely resolved;
- `probe_target`: the design-only target when uniquely resolved.

This result is the ProbeTarget derivation/audit record. It retains the
Component and provider ambiguity, the trusted decision, chosen Wire, derived
Net, document/snapshot, workflow/request, and final target without adding these
workflow facts to the small provider-neutral `ProbeTarget` value object.
`DesignEvidenceProjection` may later carry this resolution record alongside
the existing provider `DesignEvidenceContext.selection`.

## 4. Candidate-set fingerprint

The fingerprint is a stale/tamper guard, not a new design fact and not proof of
the full EDA document state.

Its input is canonical JSON containing:

1. fixed scope/version `design-selection-candidate-identities/v1`;
2. the selection document identity; and
3. the unique candidate identity tuples, sorted lexicographically by their
   canonical UTF-8 representation.

The digest is SHA-256 and is represented explicitly as `sha256:<hex>`. Sorting
makes candidate order irrelevant. Labels, provider raw payloads, primitive
objects, and unrelated document content are excluded. Validation compares the
actual identity sets as well as the digest; the digest alone is never treated
as selection authority.

Consequently, a decision for `Wire A + Component B` cannot apply to
`Wire C + Component D`, even if names match. Reordering A and B does not change
identity semantics.

## 5. Binding and validation order

The decision resolver receives trusted current `workflow_id`, trusted current
`request_correlation_id`, the current bounded selection observation plus its
host `selection_observed_at`, and an optional decision. It validates in this
order:

1. the current selection is genuinely ambiguous under existing deterministic
   rules;
2. a decision exists and has `TRUSTED_HOST_USER_EVENT` origin;
3. workflow identifiers match exactly;
4. request correlation identifiers match exactly;
5. provider, document, canonical document identity, and snapshot match;
6. current and recorded candidate identity sets match exactly;
7. candidate-set fingerprint and fingerprint scope recompute exactly;
8. `selected_object` is an exact member of the recorded and current candidate
   sets;
9. `decided_at >= selection_observed_at` for the bound observation;
10. the chosen object is a supported deterministic source;
11. source-to-target derivation produces exactly one allowed Net.

Any failure stops before ProbeTarget creation. A new provider read creates a
new observation `snapshot_id`; even an apparently unchanged visual selection
therefore requires a new decision. There is no default candidate and no
name-based recovery.

The current `SelectionContext` has no observation timestamp. Implementation
should carry `selection_observed_at` in the application-owned candidate binding
created when the capture service receives the selection. It must not pretend
that UUID `snapshot_id` itself contains time, and it does not require changing
the provider-neutral EDA Domain model.

## 6. Derivation semantics

For the accepted real shape:

```text
provider selection remains Wire + Component
provider primary_object remains null
trusted decision chooses the exact Wire identity
chosen Wire + exactly one contextual Net -> design-only NET ProbeTarget
```

The Component is never deleted, relabeled auxiliary, or hidden from
provenance. The derived Net is not a first-stage user-choice candidate because
it was not one of the provider-selected objects. If the chosen Wire yields no
Net, it is unsupported. If it yields multiple valid Nets, the result is
`DERIVED_TARGET_AMBIGUOUS`; the first decision does not resolve this second
ambiguity. A separate reviewed target-disambiguation mechanism would be needed.

The existing deterministic ProbeTarget ID may remain based on Net identity and
snapshot. The separate resolution record carries the decision provenance;
changing ProbeTarget identity to encode a workflow decision is unnecessary and
would mix concerns.

## 7. Safety and authority separation

`TrustedDesignSelectionDecision` is design-side workflow state only. It cannot:

- create or satisfy `ProbeSetupConfirmation`;
- assert a physical probe connection or wiring condition;
- create, widen, renew, or consume `TrustedOperationScope`;
- authorize a Tool, IPC request, instrument operation, or EDA write;
- replace Physical Policy;
- become measurement evidence or causal diagnosis.

The Phase 7C operation-scope and physical-policy gates remain independent and
unchanged. Phase 8B.2A code must import no Agent/model, Tool runtime, hardware,
VISA, SCPI, or JLCEDA runtime implementation.

## 8. UX contract

The trusted Host/UI renders only bounded data, for example:

```text
Multiple design objects are selected:

A. Wire — PWM_OUT
B. Component — name unavailable

Which object should be used as the design measurement target?
```

Each rendered option is internally mapped to a generated opaque choice token
and exact candidate identity. The UI may display `A`/`B`, kind, and bounded
display name, but its event returns the choice token—not free-form text and not
the display name. The host verifies that the token belongs to the still-current
challenge before issuing the decision.

Cancel, timeout, missing choice, changed selection, or unknown token leaves the
result `ambiguous_selection`. The Agent may explain the ambiguity or request a
choice, but it cannot emit the trusted UI event or call the decision issuer.

## 9. Audit semantics and bounded limitation

The structured challenge, decision, and resolution can answer without parsing
free text:

- what JLCEDA observed and why it was ambiguous;
- which exact choices were presented;
- which exact object the user selected, when, and through which trusted origin;
- the workflow, request, document, snapshot, and candidate-set binding;
- the chosen Wire, derived Net, and resulting ProbeTarget.

Phase 8B.2A proposes process-local application state for the bounded
validation. Durable production issuance, persistence, replay recovery, and
cross-process audit storage are not established. If durability is later
required, it needs a separately reviewed persistence port and versioned stored
record contract.

## 10. Schema, protocol, and Domain impact

### Evidence v1

No change is required. The trusted decision is workflow authority/provenance,
not canonical design or measurement evidence. It must not be inserted into
`protocols/evidence/v1/` ad hoc. If cross-language evidence transport is later
required, propose a new versioned schema and compatibility policy first.

### AIA-JLCEDA v1

No change is required. JLCEDA continues to report exactly what it observed:
both objects and `primary_object = null`. The trusted choice occurs above the
remote adapter in the Python Host/Application. No provider response is edited
or reinterpreted.

### Provider-neutral Domain

No generic `SelectionRole.PRIMARY/AUXILIARY` and no new field on
`DesignSelection`, `SelectionContext`, or `ProbeTarget` is proposed. Existing
Domain invariants remain unchanged. The new immutable values and resolver are
application/workflow concepts that depend on the provider-neutral EDA Domain,
never the reverse.

## 11. Proposed Red tests

Begin implementation with these failing tests:

1. Wire + Component without a decision remains `AMBIGUOUS_SELECTION` and
   creates no ProbeTarget.
2. The same selection plus a trusted exact Wire choice resolves to that Wire.
3. The chosen Wire plus one contextual Net creates the expected NET
   ProbeTarget.
4. The Component remains in `provider_selection.selected_objects` and the
   resolution audit record.
5. `provider_selection.primary_object` remains `None` after resolution.
6. model text, Tool arguments, plain free text, and an untrusted origin cannot
   manufacture a decision.
7. an arbitrary `DesignObjectRef` outside the presented candidate set is
   rejected.
8. a display-name-only choice is rejected, including another object named
   `PWM_OUT`.
9. workflow mismatch fails closed.
10. request correlation mismatch fails closed.
11. document or snapshot mismatch fails closed.
12. a changed candidate set invalidates the decision.
13. `decided_at < selection_observed_at` is stale and rejected.
14. resolution creates no physical confirmation.
15. resolution creates no `TrustedOperationScope`.
16. resolution performs zero Tool, IPC, hardware, model, EDA write, or
    highlight calls.
17. a chosen Wire with multiple derived Nets remains a second bounded
    ambiguity and creates no ProbeTarget.
18. candidate ordering changes neither fingerprint nor identity semantics.
19. full selected-object provenance is retained even when one source is
    chosen.
20. the candidate fingerprint excludes display text and raw provider payload,
    while any identity change invalidates it.

Architecture tests should enforce that the application disambiguation module
does not import JLCEDA integrations/protocol, Agent/model, operation scope,
physical policy, Tool runtime, instrument, VISA, or SCPI modules. Existing
Domain dependency tests remain unchanged.

## 12. Phase 8B.2 real revalidation plan

Only after this proposal is approved and implemented/tested:

1. authenticate the existing read-only JLCEDA connection;
2. read the active document once and selection once;
3. surface the unchanged Wire + Component ambiguity;
4. render the exact two bounded candidates in the trusted Python host UI;
5. have the user explicitly select the Wire option;
6. record and validate the bound trusted decision;
7. derive the single Net(PWM_OUT) and design-only ProbeTarget;
8. combine it with the existing trusted, non-executing physical-confirmation
   fixture and canonical recorded Hardware evidence;
9. run the existing deterministic `EngineeringEvidenceWorkflow` and project
   `TeachingDiagnosisContext`;
10. preserve 10 kHz and 30 percent as `USER_PROVIDED DESIGN_TARGET` unless the
    real schematic supplies them through an independently approved contract.

The revalidation remains zero real hardware, zero DeepSeek, zero EDA writes,
zero automatic retry, and zero fallback to fixture design data. A stale or
invalid decision ends as a bounded NOT PASS result.

## 13. Compatibility risks

- JLCEDA selection APIs remain BETA; a new observation token invalidates the
  old decision even when the UI looks unchanged. This is deliberately strict.
- The current application capture does not expose a selection observation
  timestamp; implementation must add an application-owned timestamp without
  claiming provider time.
- `canonical_id` quality is adapter-dependent. The existing mapper contract
  must remain the identity authority; display names and provider array order
  cannot compensate for a weak or missing canonical identity.
- A digest is not a durable authorization token. It guards set integrity only;
  trust still comes from the Host/UI event and exact workflow/request binding.
- Process-local decisions are lost on restart. Silent recovery or reuse is
  forbidden until durable issuance/persistence is separately designed.
- If the trusted UI is moved into the TypeScript extension, the current
  JLCEDA protocol cannot carry the decision. That requires a separate
  authenticated, versioned protocol proposal; raw/ad-hoc JSON is forbidden.
- A future provider-observed primary object is distinct evidence. It should be
  handled by provider semantics, not rewritten as a user decision.

## 14. Implemented files

- `src/ai_instrument_assistant/application/services/design_selection_disambiguation.py`
  — immutable bindings/decision/result, fingerprint, issuer boundary, and
  fail-closed resolver;
- `src/ai_instrument_assistant/application/services/eda_design_evidence.py`
  — accept a validated optional resolution and retain its provenance without
  mutating the provider selection;
- `scripts/validate_phase8b2_real_jlceda.py`
  — bounded trusted CLI challenge and one-decision revalidation flow;
- `tests/unit/application/services/test_design_selection_disambiguation.py`
  — decision and stale-binding Red/Green tests;
- `tests/unit/application/services/test_eda_design_evidence.py`
  — projection/provenance tests;
- `tests/unit/application/services/test_phase8b2_real_eda_recorded_workflow.py`
  — zero-side-effect end-to-end application tests;
- `tests/architecture/test_phase8b2_boundaries.py`
  — authority and dependency boundaries;
- this proposal and the existing Phase 8B.2 validation document after a real
  reviewed run.

No Evidence v1 schema, AIA-JLCEDA v1 protocol, Domain model, provider adapter,
or JLCEDA extension file was changed by this implementation.

## 15. Implemented behavior and automated validation

The application implementation uses frozen dataclasses and a closed Host-only
issuer path. Direct construction of `TrustedDesignSelectionDecision` is
disabled; its issuer requires a typed identity that occurs exactly once in the
current bounded candidate set. A module-private issuer token prevents the
internal constructor from becoming an accidental external-data constructor.

The candidate-set fingerprint is SHA-256 over canonical JSON with the frozen
scope above, selection document identity, and sorted candidate identities.
The resolver compares current structure, recomputed fingerprints, exact
identity sets, workflow/request/document/snapshot, and observation time before
performing the approved Wire-to-Net derivation. All non-resolved states create
no `ProbeTarget`.

The Phase 8B.2 runner now uses an asynchronous CLI prompt so the authenticated
gateway can continue servicing the connection while the user decides. Only an
exact menu key is accepted. The raw input is discarded; the stored decision
contains the exact candidate identity and bounded audit metadata. Successful
output retains provider `primary_object = null`, all provider candidates, the
decision, fingerprint, chosen Wire, derived Net, and ProbeTarget.

Automated results on 2026-09-11:

- Phase 8B.2A/8B.2 targeted application and architecture tests: 56 passed;
- full Python suite: 439 passed;
- JLCEDA TypeScript: 14 contract plus 70 adapter/architecture tests passed;
- Harness: 151 unit/contract/architecture, 38 Agent/model, and 2 Fake E2E
  tests passed against frozen commit `d347e703...`;
- strict TypeScript checks and both production builds passed;
- unified test entry passed;
- Context Pack link validation and `git diff --check` passed.

The first JLCEDA build attempt was blocked by restricted sandbox filesystem
access. The unchanged build passed under normal filesystem permission; this
was an execution-environment limitation, not a product failure.

## 16. Real validation attempt — NOT PASS

One explicitly bounded real, read-only validation was attempted on 2026-09-11.
The localhost gateway started on the configured port, but no authenticated
extension session arrived within the bounded connection window. The runner
returned:

```text
stage: connection
code: extension_not_authenticated
```

The attempt performed zero document reads, zero selection reads, zero trusted
decisions, zero EDA writes, zero hardware/backend operations, zero model
requests, zero fallback, and zero automatic retry. It observed no provider
selection and therefore cannot validate the real Wire + Component resolution
path. No provider payload, identifier, secret, or user free text was persisted.

Phase 8B.2A implementation and automated tests pass, but real compatibility is
not established by this attempt. A later retry must be separately authorized
and recorded as a new attempt; this NOT PASS record must remain historical.

## 17. Successful real revalidation — PASS

A later explicitly authorized run completed on 2026-09-11. The user reported
the runner's bounded `PASS` result and selected exact menu candidate `A`. The
raw JSON output and real provider/document/object/snapshot identifiers were not
persisted in the repository, so this closeout does not reconstruct them.

The runner's bounded PASS path requires all of the following before success:

- one authenticated real JLCEDA session;
- one active schematic document read and one selection read;
- an ambiguous provider selection retained unchanged with
  `primary_object = null`;
- a Host-issued decision bound to the current candidate-set fingerprint,
  workflow, request, document, snapshot, and observation time;
- the selected candidate occurring exactly once in that current set;
- the chosen candidate being the observed Wire;
- exactly one deterministic derived Net and a design-only ProbeTarget;
- successful cross-reference and deterministic EngineeringEvidenceWorkflow;
- empty engineering/teaching inferences and candidate next measurements.

The provider's original Component remains in the structured provider selection
carried by the resolution and projection. Candidate `A` is only a transient UI
key mapped to the exact identity at presentation time; its position and display
label do not become provider semantics or stored identity.

The successful result combined real JLCEDA structural `DESIGN_FACT` evidence,
a separate trusted design-selection decision, a trusted non-executing physical
confirmation fixture, and canonical recorded Hardware evidence. The 10 kHz and
30 percent expectations remain `USER_PROVIDED DESIGN_TARGET`; recorded
instrument data remains `PHYSICAL_FACT`, and recorded software analysis remains
`SOFTWARE_ANALYSIS`.

Without explicit tolerance, comparisons remain
`INDETERMINATE / TOLERANCE_UNSPECIFIED`. The separate explicit one-percent
fixture may produce `MATCH` only under that stated tolerance. The run produced
no diagnosis or causal inference.

The successful run used real JLCEDA read access, but zero real DS1102Z-E calls,
zero Hardware backend/runtime/service execution, zero DeepSeek/AgentLoop calls,
zero EDA writes, zero automatic retry, and zero fixture fallback pretending to
be real JLCEDA. Phase 8B.2A is complete within those bounded claims.
