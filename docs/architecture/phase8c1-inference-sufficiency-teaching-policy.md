# Phase 8C.1 — Inference Sufficiency and Teaching Claim Policy

Status: **COMPLETE — implementation and architecture review passed**

## Implementation record

The reviewed Phase 8C.1 slice is implemented under
`src/ai_instrument_assistant/application/reasoning/`. The implementation is a
deterministic application policy, not an Agent or publication pipeline. It adds
no model, EDA, Hardware, Tool, authorization, or transport dependency.

The deliberately small implementation surface is:

- immutable `ClaimSubjectRef`, `ClaimPermission`, `AllowedClaimEnvelope`, and
  `DeterministicFallback` values;
- closed `TeachingGoal` values `EXPLAIN_MEASUREMENT`, `ASSESS_REQUIREMENT`, and
  `EXPLAIN_CAUSE`;
- exact claim forms beneath the eight reviewed `ClaimKind` values;
- a deterministic context fingerprint and subject/comparison references;
- `InferenceSufficiencyEvaluator`, with no knowledge or causal rule registry
  enabled; and
- an evidence-only fallback projection containing only allowed restatement,
  comparison, and limitation slots.

Every SHA-256 value in this package is a deterministic **content identity
only**. This includes the bounded `TeachingDiagnosisContext` fingerprint,
`AllowedClaimEnvelope.envelope_id`, subject keys, and comparison composite
references. None is authentication, authorization, a trust/freshness/provenance
proof, a persistent identity, or a digital signature. Trust continues to come
from structured provenance, trusted Host/application state, deterministic
policy evaluation, and the later Grounding and Egress gates.

The architecture below includes later-phase extension points. Where its
earlier conceptual names differ, the implemented names above are authoritative
for Phase 8C.1. In particular, this phase uses a closed `TeachingGoal` directly
rather than adding a persistence/issuance model, and it uses a finite context
fingerprint rather than claiming a provider revision or durable identity.

## 1. Decision

Phase 8C.1 introduces a provider-neutral, deterministic policy boundary that
decides which classes of claims may be attempted from one immutable
`TeachingDiagnosisContext`. It does not generate prose, diagnose a circuit,
call a model, fetch an artifact, propose executable Tool arguments, or authorize
any operation.

The frozen principles are:

```text
evidence != inference
comparison != diagnosis
correlation != causality
ProbeTarget != physical connection truth
VERIFIED_LINK != design immutability
numerical proximity != MATCH without an explicit acceptance criterion
```

The policy is a necessary precondition for a future Teaching Agent, not a
replacement for Grounding, Egress, operation scope, or Physical Policy.

## 2. Scope and non-goals

This reviewed design and implementation establish:

- a deterministic `InferenceSufficiencyEvaluator`;
- a minimal immutable `AllowedClaimEnvelope`;
- structured goal binding and claim taxonomy;
- evidence/comparison reference rules;
- quality, warning, coherence, contradiction, and limitation constraints;
- a future structured candidate-validation boundary;
- deterministic fallback behavior;
- proposal-only next-measurement semantics and later phase boundaries.

It does not change a canonical schema, invoke JLCEDA, hardware, a backend,
DeepSeek, or AgentLoop, or create an autonomous
measurement loop. Phase 8C.1 enables no causal claim by default and defines no
electronics-fault-specific rule.

## 3. Position in the architecture

```text
trusted Host goal classification
              |
immutable TeachingDiagnosisContext + trusted context reference
              |
              v
InferenceSufficiencyEvaluator (deterministic application policy)
              |
              v
AllowedClaimEnvelope (no prose, no execution authority)
              |
              v
future model adapter / structured ClaimCandidateSet
              |
              v
Engineering Claim Grounding (deterministic, additive)
              |
              v
existing Grounding + Egress boundaries
              |
              v
published structured rendering OR deterministic evidence-only fallback
```

The evaluator belongs in the provider-neutral application layer. It may depend
on engineering-evidence domain types and narrow policy abstractions. It must not
depend on Harness, DeepSeek, JLCEDA, Rigol, VISA, SCPI, WebSocket, drivers,
artifacts stores, Tool runtimes, or concrete adapters.

## 4. Two independent semantic axes

The listed fact categories are already represented by the evidence model and
must not be duplicated as competing claim types. Phase 8C therefore uses two
orthogonal axes.

### 4.1 Support subject category

The first axis identifies what authority a claim refers to:

| Subject category | Existing authority | Required attribution |
| --- | --- | --- |
| `DESIGN_FACT` | `DesignEvidenceItem` | JLCEDA/design observed, including snapshot limitation |
| `DESIGN_TARGET` | `EngineeringTarget` and its source evidence | design-derived or user-provided exactly as recorded |
| `PHYSICAL_FACT` | located instrument evidence | instrument measured |
| `SOFTWARE_ANALYSIS` | located analysis evidence | software calculated |
| `SIMULATED_EVIDENCE` | located simulated evidence | simulated, never physical |
| `COMPARISON_RESULT` | existing deterministic comparator | system compared using named/versioned comparator |
| `CONTEXT_CONSTRAINT` | warning, limitation, coherence, quality, or unresolved question | system/context metadata |
| `GENERAL_KNOWLEDGE` | separately reviewed teaching knowledge | general concept, never case evidence |

`INFERENCE` is deliberately not a source category for new claims. A new
inference is the output under evaluation and cannot support itself.

### 4.2 Claim kind

The second axis describes semantic strength:

| Claim kind | Meaning | Phase 8C.1 default |
| --- | --- | --- |
| `EVIDENCE_RESTATEMENT` | Exact bounded restatement of one structured fact, analysis, target, availability state, or provenance | Allowed per referenced item |
| `DETERMINISTIC_COMPARISON` | Exact restatement or direct implication of an existing `ComparisonResult` | Allowed per referenced result |
| `LIMITATION_STATEMENT` | Exact statement of a warning, limitation, quality, coherence, or unresolved state | Allowed and sometimes mandatory |
| `EDUCATIONAL_EXPLANATION` | General concept not asserted about this circuit | Allowed only with reviewed knowledge support |
| `ENGINEERING_INFERENCE` | A rule-derived case-specific conclusion beyond direct comparison | Blocked unless a reviewed deterministic rule is satisfied |
| `HYPOTHESIS` | Explicit possible explanation with unresolved alternatives | Blocked unless a reviewed hypothesis rule is satisfied |
| `CAUSAL_DIAGNOSIS` | Claim that a cause produced an observed effect | Blocked unless a reviewed causal rule is satisfied; no such rule exists now |
| `NEXT_MEASUREMENT_PROPOSAL` | Proposal to gather evidence for a referenced unresolved question | Deferred to Phase 8C.3 and never execution authority |

This avoids treating `OBSERVED_FACT`, `SOFTWARE_ANALYSIS`, and `DESIGN_TARGET`
as both evidence categories and claim classes. Their identity remains on the
support-reference axis.

## 5. Claim strength and sufficiency

Numeric confidence scores are rejected for the baseline because they would
suggest unsupported precision. Each bounded claim permission instead records:

- `disposition`: `ALLOW` or `BLOCK`;
- `support_basis`: `EXACT_RESTATEMENT`, `DETERMINISTIC_DERIVATION`,
  `REVIEWED_MULTI_EVIDENCE_RULE`, or `INSUFFICIENT`;
- stable reason codes;
- exact subject and support references;
- mandatory attribution and limitation qualifiers;
- an optional reviewed rule identifier and version.

Omitted, unknown, malformed, or unrecognized claim kinds are blocked. An
`ALLOW` is scoped to the exact subject and references in one envelope; it is not
a global permission to make every claim of that class.

## 6. Trusted goal binding

Inference sufficiency depends on the requested task, but free text must not be
the deterministic authority. Phase 8C.1 accepts only the closed `TeachingGoal`
enum at its application boundary. Unknown strings are rejected. A later
trusted Host/Application issuance boundary may add durable workflow binding,
but does not exist in this phase.

The implemented goal mapping is:

| `TeachingGoal` | Maximum Phase 8C.1 surface |
| --- | --- |
| `EXPLAIN_MEASUREMENT` | exact evidence and limitation restatements; comparison slots may be suppressed |
| `ASSESS_REQUIREMENT` | the above plus supported deterministic comparison slots |
| `EXPLAIN_CAUSE` | the same supported slots; inference, hypothesis, and diagnosis remain blocked |

The following remains a later-phase durable goal authority design:

- a goal identifier;
- one exact goal class;
- the referenced teaching-context identity;
- the trusted workflow/request identities where available;
- issuance time and trusted origin;
- optional bounded display text that is non-authoritative.

Conceptual later goal classes are:

| Goal class | Maximum default claim surface |
| --- | --- |
| `EXPLAIN_EVIDENCE` | restatements, limitations, supported general teaching |
| `ASSESS_COMPLIANCE` | the above plus exact deterministic comparison implications |
| `INVESTIGATE_CAUSE` | the above; hypotheses/diagnoses still require separate reviewed rules |

A missing, stale, mismatched, or unknown goal fails closed to evidence-summary
only. A stronger goal never creates evidence or increases a rule's sufficiency;
it only selects which already-supported claim classes are relevant. Model text
cannot create or alter the trusted goal class.

## 7. Context identity and staleness

`TeachingDiagnosisContext` intentionally has no independent evidence authority
or context identifier. In Phase 8C.1, the evaluator computes a deterministic
SHA-256 fingerprint of its finite structured projection. Presentation `label`
fields are excluded; source, value, unit, quality, provenance, comparisons,
warnings, limitations, coherence, and unresolved state remain bound. A later
durable boundary may wrap this in a `ReasoningEvaluationRequest` and trusted
`TeachingContextReference`.

The reference contains the engineering context UUID, deterministic projection
fingerprint and algorithm version, workflow identity, and assembly time. The
fingerprint binds the exact finite projection supplied to evaluation; it is not
a provider revision and does not prove JLCEDA immutability. A changed projection
or mismatched reference invalidates the envelope.

## 8. Evidence and comparison references

Free-text citations never establish support. Claim support uses a closed union:

- `DesignEvidenceRef(evidence_id)`;
- `TargetRef(target_id)`;
- `MeasurementEvidenceRef(measurement_context_id, collection, ordinal, label,
  metric, category)` reusing `MeasurementEvidenceLocator` semantics;
- `ComparisonRef(target_id, observed_ref, comparator_name,
  comparator_version)`;
- `ContextConstraintRef(projection_fingerprint, collection, ordinal)` for a
  warning, limitation, unresolved question, quality, or coherence field;
- `KnowledgeRef(topic_id, corpus_version, content_digest)` for reviewed general
  teaching material only.

Every reference is resolved against the exact immutable input before policy
evaluation. Unknown, duplicate, stale, cross-context, self-referential, or
category-inconsistent references are rejected. Display labels and array order
alone do not establish evidence identity. Ordinal constraint references are
safe only because they are also bound to the exact projection fingerprint.

## 9. Minimal `AllowedClaimEnvelope`

The immutable provider-neutral envelope contains no model prose and no hardware
control type. Its implemented fields are:

- `envelope_id`, `policy_name`, and `policy_version`;
- exact finite context fingerprint;
- exact typed `TeachingGoal`;
- a tuple of subject-scoped `ClaimPermission` records;
- referenced unresolved questions;

There is intentionally no `evaluated_at`: current time must not make identical
inputs produce different policy output. Mandatory constraints are stored on
the exact permissions that require them.

Each `ClaimPermission` contains claim kind, subject reference, disposition,
support basis, supporting evidence/comparison/knowledge references, mandatory
qualifier codes, and optional reviewed rule ID/version. The envelope contains
neither free-form answer text nor a confidence percentage.

An `ALLOW` is only a necessary local prerequisite. It never means “publish
now.” Phase 8C.2 candidate publication must separately prove that the exact
slot is allowed; subject and all support refs resolve; source attribution is
correct; every mandatory obligation and obligation reference is semantically
satisfied; no forbidden strengthening occurred; Grounding passes; and final
Egress passes. The Phase 8C.1 helper is therefore named
`publication_prerequisites_satisfied`, not `can_publish`.

It also contains no operation name, Tool arguments, channel command, budget,
`TrustedOperationScope`, `ProbeSetupConfirmation`, Physical Policy decision,
IPC request, or callback. Package dependency tests must enforce that separation.

## 10. Deterministic evaluation order

`InferenceSufficiencyEvaluator.evaluate(context, goal)` performs:

1. validate context-reference and goal bindings;
2. inventory exact evidence, targets, comparisons, constraints, and unresolved
   questions;
3. validate every internal reference and source/category relation;
4. derive mandatory quality, warning, coherence, snapshot, and availability
   qualifiers;
5. create subject-scoped exact-restatement permissions;
6. create comparison permissions solely from existing comparator results;
7. emit explicit BLOCK entries because no reviewed knowledge, inference,
   hypothesis, causal, or next-measurement rule is installed;
8. block every unsupported or unrecognized class explicitly;
9. return a deeply immutable envelope with stable reason codes.

It does not generate natural language or ask a model whether evidence is
sufficient. It does not recompute tolerances or replace the existing comparator.

## 11. Deterministic comparison policy

The existing `DeterministicEngineeringComparator` remains authoritative.

- `INDETERMINATE / TOLERANCE_UNSPECIFIED` permits the recorded target,
  observation, deterministic difference, and the statement that compliance
  cannot be determined because no acceptance tolerance exists.
- It blocks `MATCH`, `MISMATCH`, pass, fail, correct, faulty, normal, abnormal,
  close-enough, and outside-range claims.
- `MATCH / WITHIN_TOLERANCE` or `WITHIN_RANGE` permits only the direct statement
  that the referenced observation is within the recorded criterion.
- `MISMATCH / OUTSIDE_TOLERANCE` or `OUTSIDE_RANGE` permits only the direct
  statement that it is outside the recorded criterion.
- Discrete equal/different results may be restated exactly.

Interpretation always binds the status and exact reason together. Another
`INDETERMINATE` reason, such as `MEASUREMENT_MISSING`, does not receive the
`TOLERANCE_UNSPECIFIED` claim or obligations. It may expose the exact status
only while preserving its actual reason, and criterion/compliance statements
remain blocked. The composite comparison identity includes the exact reason,
and fallback carries the original permission unchanged.

Even an explicit mismatch supplies an effect/compliance observation, not a
cause. Product-level words such as “pass” remain blocked unless a separate
trusted acceptance policy explicitly maps that criterion to such a verdict.

## 12. Hypothesis semantics

A hypothesis is a machine-readable claim kind, not softened diagnosis prose.
It must contain:

- a reviewed hypothesis rule ID/version;
- exact motivating evidence and comparison references;
- the unresolved question it addresses;
- explicit alternative-hypothesis identifiers or an unresolved-alternatives
  marker;
- mandatory uncertainty and limitation qualifiers.

Changing “X caused Y” to “possibly X caused Y” does not make it supported. A
candidate typed as `HYPOTHESIS` but containing a diagnostic/certain relation is
structurally inconsistent and rejected. A hypothesis cannot be rendered as a
fact or diagnosis, and it cannot support a later claim merely by existing.

Phase 8C.1 initially has no registered electronics hypothesis rules, so its
default envelope blocks case-specific hypotheses while preserving the model
surface needed for later reviewed rules.

## 13. Causal-diagnosis sufficiency

Causal diagnosis requires a registered deterministic `CausalRule` with a
stable ID/version. A rule may allow one exact causal claim only when all its
predicates are satisfied:

1. the effect is established by relevant available observations and, where
   compliance is asserted, an explicit trusted criterion;
2. the design facts and physical evidence are linked by a sufficiently trusted
   cross-reference;
3. cause-specific observed/configuration evidence exists; a target or general
   knowledge statement is not cause evidence;
4. every required measurement/evidence role is present with rule-accepted
   quality;
5. source attribution, workflow, channel, snapshot, and temporal requirements
   are consistent;
6. contradictions are absent or handled by an explicit rule branch;
7. material warnings and coherence limitations are represented;
8. named alternative explanations are excluded by discriminating evidence or
   remain explicitly unresolved;
9. the rule declares whether observational evidence is sufficient or requires
   an intervention/repeated observation.

If any predicate is missing, the causal claim is blocked. A single mismatch,
correlation, `VERIFIED_LINK`, or numerical difference is never sufficient.
There are no approved causal rules in Phase 8C.1, so `CAUSAL_DIAGNOSIS` remains
globally blocked after this design.

### Synthetic future causal structure

A future provider-neutral example could contain: an explicitly observed design
configuration value, an explicit acceptance criterion, a verified measurement
showing the effect, an upstream discriminating observation, a downstream
observation, and a reviewed controlled-change record showing the effect changes
as the candidate cause changes while other declared conditions remain fixed.
Alternative explanations and measurement quality are recorded. Only a reviewed
rule designed for that evidence pattern could then allow a bounded causal
claim. Without the controlled/discriminating evidence, the same data supports
at most a hypothesis.

This example defines structural needs; it does not assert a rule for timers,
resistors, probes, clocks, or any other specific fault.

## 14. Quality, warning, and availability constraints

- Available good evidence may be restated with exact source and provenance.
- Degraded evidence may be restated only with its degraded status and all
  material warnings required by the relevant permission.
- Unavailable evidence permits only an availability/limitation statement; no
  value may be borrowed from a target, another source, simulation, or prior run.
- Failed or unknown measurement context blocks positive measurement and
  case-specific inference claims.
- Default multi-evidence inference and causal rules require good evidence.
  A future rule that accepts degraded evidence must enumerate accepted warning
  codes and mandatory qualifiers explicitly.
- Unknown quality or warning semantics fail closed for stronger claims.

Warnings are not optional prose. Their structured references become mandatory
constraints on affected claim permissions, so omission by a model is a
grounding failure.

## 15. Coherence and snapshot constraints

- `same_artifact` relates only the recorded software analyses. It does not make
  an instrument result part of the same artifact.
- `sequential_same_session` permits “sequential observations in one session”
  and blocks simultaneous, atomic, or same-instant claims.
- Missing/unknown coherence blocks claims that require a shared acquisition.
- JLCEDA `snapshot_id` remains observation identity only.
- `VERIFIED_LINK` proves the bounded association encoded by the cross-reference;
  it does not prove the EDA design was immutable between observation and
  measurement.

These limitations become mandatory constraint references whenever a claim
relates design and measurement evidence.

## 16. Contradictory and multi-source evidence

Instrument and software evidence remain separate. The evaluator never averages,
ranks, silently selects, or synthesizes a value.

- Exact source-labelled values may each be restated.
- Deterministically unequal normalized values may be described as
  `MULTI_SOURCE_VALUES_DIFFER`, not automatically as a material contradiction.
- Numeric closeness or material disagreement requires an explicit criterion;
  the evaluator invents none.
- Mutually exclusive discrete facts, opposite comparison outcomes against the
  same explicit criterion, or an existing bounded contradiction marker may be
  classified as `CONTRADICTORY_EVIDENCE_PRESENT`.
- Either state becomes a mandatory limitation and blocks causal diagnosis
  unless a reviewed rule explicitly resolves it.

The policy may state that estimates differ and list both sources. It cannot say
which one is correct without additional trusted evidence.

## 17. General teaching knowledge boundary

General educational explanation is separate from circuit evidence. A future
`TeachingKnowledgePort` may supply immutable, reviewed `KnowledgeRef` entries
from a versioned allowlist. For example, a reviewed PWM topic may explain that
duty cycle is the fraction of a period spent high.

General knowledge:

- may explain a universal concept relevant to an observed metric;
- must cite a reviewed knowledge reference, not model memory as authority;
- cannot claim a property, component value, configuration, topology, or cause
  for the user's circuit;
- cannot satisfy a physical-evidence, comparison, hypothesis, or causal-rule
  predicate;
- must remain visibly educational rather than case-specific.

Until such a reviewed knowledge catalog exists, the deterministic fallback is
evidence-only and the envelope blocks unreferenced educational assertions.

## 18. Current PWM scenario

For the Phase 8B.3 conceptual context, the evaluator may allow:

- restatement that `PWM_OUT` was observed in the bounded JLCEDA design context,
  with observation-identity-only snapshot limitation;
- exact attribution that 10 kHz and 30% are user-provided targets;
- exact source-labelled instrument facts and software analyses actually present
  in the supplied context, including quality and warnings;
- the bounded `VERIFIED_LINK` association without an immutability claim;
- exact recorded numerical differences, if present in comparison results;
- `INDETERMINATE / TOLERANCE_UNSPECIFIED` and the direct conclusion that
  compliance cannot currently be determined;
- relevant limitations and unresolved questions.

It must block “PWM is correct,” “PWM is faulty,” “close enough,” “passes,”
“fails,” and any timer/configuration causal claim. With no registered rule it
also blocks a case-specific causal hypothesis. No numeric value omitted from the
supplied context or bounded validation record may be reconstructed.

## 19. Synthetic explicit-tolerance scenario

Given a user-provided 10 kHz target with an explicit trusted ±1% tolerance and
an 8 kHz observation linked by verified evidence, the existing comparator may
produce `MISMATCH / OUTSIDE_TOLERANCE`.

The envelope may allow the deterministic claim that the referenced observed
frequency is outside the specified ±1% tolerance, with exact source and
criterion references. It still blocks “the timer is wrong,” “the clock caused
the error,” or any other causal diagnosis. The mismatch establishes a bounded
criterion failure, not its cause.

## 20. Future structured claim candidates

Phase 8C.2 should require the model adapter to produce a bounded
`ClaimCandidateSet`, not unstructured prose as the authority. Each candidate
must contain a claim ID, machine-readable claim kind, subject reference, exact
support/comparison/knowledge references, required limitation references,
optional reviewed rule reference, and bounded presentation text.

The structural type determines semantics. Presentation wording cannot upgrade
or downgrade the claim kind. The candidate is accepted only if it matches one
exact `ALLOW` permission in the envelope and preserves every mandatory
qualifier. Unknown fields and claim kinds fail closed.

If cross-language exchange is required, this candidate/envelope format belongs
in a new versioned Agent-claims protocol. It must not be added to Evidence v1.

## 21. Grounding Guard integration

The existing Phase 7C Grounding Guard remains valid but insufficient for Phase
8C by itself. It consumes `TeachingEvidenceContext` and checks a constrained
English measurement surface. It cannot authoritatively resolve design-evidence
UUIDs, targets, `ComparisonResult`, trusted goal bindings, hypotheses, causal
rules, or next-measurement proposals.

Phase 8C.2 should add an `EngineeringClaimGroundingGuard` that validates
structured candidates against the exact `AllowedClaimEnvelope` and teaching
context reference. This is additive: it must not weaken, bypass, or reinterpret
the existing numeric/source/quality/warning/coherence/artifact checks. Unknown
or stale references, missing qualifiers, unsupported classes, and prose/type
semantic conflict are rejected before publication.

## 22. Egress Guard integration and ordering compatibility

The existing frozen Harness boundary inspects raw model output with Egress
before its English Grounding Guard. This protects secrets, paths, resource IDs,
commands, and arrays before deeper processing. The proposed shorthand
“structural parsing -> Grounding -> Egress -> publish” must not silently reverse
that established confidentiality boundary.

The compatible future pipeline is therefore two-pass:

```text
raw model candidate
  -> existing Egress pre-scan
  -> structural ClaimCandidateSet parse
  -> engineering-claim grounding against AllowedClaimEnvelope
  -> deterministic rendering
  -> final Egress inspection
  -> existing applicable Grounding checks
  -> publish
```

Both semantic grounding and Egress must pass. `Egress SAFE` never implies
grounding support, and grounding support never implies safe disclosure. Nothing
is published and annotated afterward.

## 23. Deterministic fallback

Any parse, reference, attribution, sufficiency, limitation, grounding, or Egress
failure discards the unsupported candidate. There is no model retry, Tool retry,
artifact fetch, or remeasurement.

The deterministic fallback renders only permissions already marked
`EXACT_RESTATEMENT` or `DETERMINISTIC_DERIVATION`, in this order:

1. what design/target/measurement evidence is available, source-labelled;
2. what the deterministic comparator recorded;
3. mandatory quality, warning, coherence, and snapshot limitations;
4. what cannot be concluded;
5. which referenced information is missing or unresolved.

It emits no hypothesis, causal diagnosis, invented tolerance, new evidence, or
next-measurement proposal. The fallback itself must pass structured grounding,
the applicable existing Grounding checks, and Egress. A fixed no-claim last
resort remains defense in depth.

## 24. Next-measurement proposal semantics

`NEXT_MEASUREMENT_PROPOSAL` is a recommendation class, never an action or
authorization. Phase 8C.1 defines its future constraints but emits none; Phase
8C.3 owns implementation.

A valid immutable proposal must reference:

- one existing unresolved question;
- the exact evidence/comparison that motivates it;
- a provider-neutral target candidate;
- the metric or evidence role sought;
- an allowlisted information-purpose code explaining what distinction the
  measurement could resolve;
- explicit proposal limitations;
- separate-execution preconditions such as new trusted operation scope and, for
  a physical measurement, new physical confirmation.

It contains no Tool name, raw operation, SCPI, VISA resource, IPC message,
invocation budget, or pre-approved policy decision. “Confirmation required” is
advisory metadata; only the existing Physical Policy can decide execution.
Accepting or displaying a proposal causes zero Tool, IPC, or hardware effects.

## 25. Execution separation and no autonomous loop

The complete Phase 8C reasoning path is read-only over existing bounded
evidence. Neither evaluator, envelope, structured claim, hypothesis, diagnosis,
nor proposal may import, create, carry, or mutate:

- `TrustedOperationScope` or its budget;
- `ProbeSetupConfirmation`;
- Physical Policy results;
- Hardware Tool arguments or runtime;
- JLCEDA write/highlight actions;
- IPC or transport clients.

A later proposal must return to a separate trusted Host workflow for fresh
authorization and physical confirmation. No observe -> diagnose -> measure ->
rediagnose loop is introduced.

## 26. Evidence v1 and `TeachingDiagnosisContext` impact

Evidence v1 receives **no change**. It remains raw/composed evidence exchange,
and its Phase 8 inference collection remains empty. Claim policy, candidates,
and decisions are reasoning/application state, not evidence.

`TeachingDiagnosisContext` remains immutable evidence input. It is not expanded
with claim permissions, model prose, inferred facts, diagnoses, or execution
state. `AllowedClaimEnvelope`, accepted claims, and audit decisions live
alongside it and reference it through the trusted projection identity.

If later cross-language validation is required, a separate
`protocols/agent-claims/v1/` should be proposed and reviewed. Its schema would be
wire-format authority only; policy rules and cross-object reference semantics
remain deterministic application logic.

## 27. Audit chain

The future append-only audit chain is:

```text
trusted goal event
  -> TeachingContextReference + projection fingerprint
  -> InferenceSufficiency policy/version + envelope ID
  -> bounded model request ID
  -> raw candidate retention policy outcome (raw unsafe text not persisted)
  -> parsed ClaimCandidateSet ID
  -> per-claim permission/reference/rule decision
  -> engineering Grounding decision
  -> existing Grounding decision
  -> Egress decision
  -> published claim IDs or deterministic fallback ID
```

The audit record stores stable categories, IDs, versions, counts, and bounded
reason codes. It must not persist secrets, full serials, VISA resources, raw
provider payloads, unrestricted artifacts, rejected unsafe prose, or stack
traces. It must answer “why was this claim allowed?” by resolving the exact
goal, context, permission, support references, rule version, and guard results.

## 28. Bounded failure behavior

| Condition | Deterministic result |
| --- | --- |
| Missing/stale context reference | Block all case-specific claims; evidence-safe fallback only |
| Missing/unknown trusted goal | Evidence-summary-only envelope |
| Missing target | No compliance claim; record target unresolved |
| Missing tolerance | Only difference plus `TOLERANCE_UNSPECIFIED`; no MATCH/pass/fail |
| Missing physical evidence | No physical measurement or case inference claim |
| Unverified cross-reference | No authoritative design-to-measurement comparison/diagnosis |
| Degraded quality | Exact restatement with warnings; stronger rules blocked by default |
| Unavailable observation | Availability statement only; no borrowed value |
| Conflicting/divergent sources | Preserve each source and mandatory conflict limitation; no averaging |
| Unknown evidence/comparison reference | Reject claim as ungrounded |
| Unsupported source attribution | Reject claim; do not relabel source |
| Unsupported inference/hypothesis/diagnosis | Reject candidate; deterministic fallback |
| Candidate cannot be parsed | Reject whole candidate set; deterministic fallback |
| Required limitation omitted | Reject affected candidate or whole atomic response |
| Proposal lacks unresolved question/rationale | Reject proposal; zero execution effect |
| Guard/evaluator internal failure | Bounded fail-closed result; no candidate publication or retry |

An atomic response policy is preferred initially: if any case-specific claim is
unsupported, discard the entire model candidate and render the deterministic
fallback. This avoids retaining prose whose dependencies may cross claim
boundaries.

## 29. Red test plan

Phase 8C.1 implementation should begin with failing tests for:

1. exact physical-fact restatement is allowed with instrument attribution;
2. software analysis cannot be attributed to the instrument;
3. user-provided target cannot be attributed to JLCEDA;
4. no-tolerance context permits compliance-undetermined but blocks MATCH,
   pass, fail, normal, abnormal, and close-enough claims;
5. explicit-tolerance MISMATCH permits only outside-criterion restatement;
6. mismatch alone never permits a causal diagnosis;
7. unsupported diagnosis is blocked with stable reason codes;
8. hypothesis is machine-typed and cannot be upgraded by prose;
9. diagnosis wording labelled as hypothesis is rejected;
10. unknown, stale, and cross-context evidence references fail closed;
11. degraded evidence requires quality and every material warning;
12. unavailable evidence cannot borrow a target or another source value;
13. conflicting sources remain separate and are never averaged;
14. sequential coherence blocks simultaneous/atomic claims;
15. `VERIFIED_LINK` does not permit a design-immutability claim;
16. general knowledge can explain an approved concept but cannot become a
    circuit fact or satisfy a causal rule;
17. unknown knowledge reference is blocked;
18. missing/unknown goal yields evidence-summary-only permissions;
19. stronger goal does not increase evidence sufficiency;
20. envelope is deeply immutable and contains no model prose or execution
    authority types;
21. next-measurement proposal without an unresolved question or purpose is
    blocked;
22. a valid proposal creates no scope, confirmation, Tool, IPC, or hardware
    effect;
23. model candidate cannot create or widen Tool scope;
24. parse failure, source error, unsupported causality, and limitation omission
    each produce the same no-retry deterministic fallback path;
25. fallback contains no unsupported claims and passes Grounding plus Egress;
26. Evidence v1 schemas and existing comparison semantics remain byte-stable;
27. application reasoning policy has no provider, Harness, model, transport,
    driver, artifact-store, or Hardware runtime dependency.

All examples use synthetic/recorded evidence. No external system belongs in
ordinary tests.

## 30. Implemented files and policy catalog

The Phase 8C.1 implementation is:

```text
src/ai_instrument_assistant/application/reasoning/
  __init__.py
  models.py                    # goals, refs, permissions, envelope
  inference_sufficiency.py     # deterministic evaluator; no reviewed rule registry enabled
  fallback.py                 # bounded permission projection, no prose/retry

tests/unit/application/reasoning/
  test_evaluator.py
  test_models.py

tests/architecture/
  test_phase8c_reasoning_boundaries.py
```

Implemented ALLOW reasons are `EXACT_EVIDENCE_AVAILABLE`,
`EXACT_TARGET_AVAILABLE`, `EXACT_LIMITATION_AVAILABLE`,
`EVIDENCE_UNAVAILABLE`, and
`EXISTING_COMPARISON_SUPPORTS_STATEMENT`. Implemented fail-closed reasons are
`UNKNOWN_OR_STALE_SUBJECT`, `ACCEPTANCE_CRITERION_UNAVAILABLE`,
`COMPARISON_DOES_NOT_SUPPORT_CRITERION`, `GOAL_NOT_RELEVANT`,
`NO_REVIEWED_KNOWLEDGE_SOURCE`, `NO_REVIEWED_INFERENCE_RULE`,
`NO_REVIEWED_HYPOTHESIS_RULE`, `NO_REVIEWED_CAUSAL_RULE`, and
`NEXT_MEASUREMENT_DEFERRED`.

Publication obligations cover exact attribution for design observations,
user statements, user/design targets, instrument facts, software analyses, and simulated
evidence; unavailable/degraded state; material warnings; sequential coherence;
the non-atomic qualification; observation-identity and non-immutability
limits; tolerance-unspecified/compliance-undetermined state; and exact
comparison reason preservation. `ClaimPermission.publication_prerequisites_satisfied`
checks only these local prerequisites; omitting any required item fails closed,
and success still does not bypass structured candidate validation, Grounding,
or Egress.

Comparison composite references hash the canonical metric, target UUID,
measurement context/collection/ordinal/metric/category, structured expected and
observed values, difference, relative difference, status/reason, and comparator
name/version. Locator display labels and rendered prose are excluded. All
reference hashes remain bound to the finite context fingerprint.

The automated TDD scenarios cover the PWM no-tolerance case, explicit ±1%
mismatch, degraded evidence, unavailable evidence, conflicting sources,
source-misattribution attempts, stale/unknown references, typed-goal rejection,
goal monotonicity, canonical ordering, fallback constraints, frozen schemas,
and forbidden dependencies/authority types.

Closeout tests additionally prove that content hashes carry no security
authority, an ALLOW permission exposes no automatic publication method, and
non-tolerance `INDETERMINATE` reasons cannot be rewritten as
`TOLERANCE_UNSPECIFIED` by evaluation or fallback.

A reviewed general-knowledge integration, if approved later, adds only a
provider-neutral port and an adapter outside the policy core. Phase 8C.2 may
propose `protocols/agent-claims/v1/` plus an adapter-side structured parser and
engineering grounding integration; it must not alter Evidence v1.

## 31. Recommended sub-phase decomposition

### Phase 8C.1 — deterministic claim-policy core

After this architecture review: implement immutable goal/reference/envelope
models, deterministic sufficiency evaluation, closed rule registry with no
causal electronics rules, PWM and synthetic tolerance tests, architecture
tests, and an evidence-only fallback projection. No model integration.

### Phase 8C.2 — structured model candidate and guarded publication

Define a separate versioned candidate contract if cross-language exchange is
needed; integrate a fake/scripted model first; validate claim candidates against
the envelope; add engineering Grounding and the compatible two-pass Egress
pipeline; publish only guarded structured rendering or deterministic fallback.
No next-measurement generation and no real execution.

### Phase 8C.3 — proposal-only next measurement

Add unresolved-question-bound proposal models and deterministic proposal
sufficiency. Proposals remain non-executable and return to a separate trusted
workflow for any later action. No autonomous loop.

Any real model validation should be a separately authorized validation subphase
after 8C.2, not an implicit part of policy implementation.

## 32. Phase 8C.2 entry criteria

Phase 8C.2 may begin only when:

- Phase 8C.1 models/evaluator are reviewed, implemented, committed, and covered
  by the Red tests above;
- exact context and goal binding is deterministic and stale references fail
  closed;
- every claim kind has an explicit scoped ALLOW/BLOCK result;
- Evidence v1 and `TeachingDiagnosisContext` evidence semantics remain
  unchanged;
- zero causal rule is enabled unless separately reviewed;
- the deterministic fallback is independently grounded and egress-safe;
- architecture tests prove zero execution/authorization dependencies;
- the new candidate protocol need is decided explicitly rather than hidden in
  language-specific DTOs.

## 33. Phase 8C.3 entry criteria

Phase 8C.3 may begin only when:

- Phase 8C.2 structured candidate parsing and guarded publication are reviewed
  and fail closed;
- proposal claim type cannot be confused with a Tool request or authorization;
- unresolved-question and evidence-reference identity are available to the
  proposal policy;
- an allowlist of proposal purposes and provider-neutral target semantics is
  reviewed;
- tests prove displaying/accepting a proposal causes zero Tool, IPC, scope,
  confirmation, and hardware effects;
- renewed authority is explicitly delegated to a separate future Host workflow.

## 34. Compatibility findings

1. **Evidence v1 must not carry reasoning state.** Its inference collection is
   currently frozen empty, so filling it would be a semantic break. The new
   envelope and claims must live alongside the context.
2. **`TeachingDiagnosisContext` has no stable external identity.** A trusted
   projection reference/fingerprint is required outside the model to support
   stale-reference rejection and audit.
3. **Existing Grounding is too narrow, not wrong.** It validates constrained
   English claims over `TeachingEvidenceContext`; Phase 8C needs additive
   structured engineering-claim grounding rather than weakened regexes or
   untrusted model self-evaluation.
4. **Guard ordering needs two passes.** The frozen Egress-first inspection of
   raw output must remain, while Phase 8C also needs structural grounding before
   the final rendered text passes Egress and publication.
5. **Comparison results lack independent IDs.** A deterministic composite
   `ComparisonRef` can bind target, observed locator, and comparator version
   without changing Evidence v1.
6. **General knowledge has no current reviewed authority.** Model memory alone
   cannot support published teaching claims; a versioned knowledge reference is
   required or the claim remains blocked.
7. **No causal rule registry exists.** Causal diagnosis must remain blocked; a
   mismatch is not a substitute.

None of these findings requires a production or schema change in this design
round.

## 35. Bounded limitations

- This implementation defines a structured policy boundary, not arbitrary natural-language
  semantic verification.
- The initial evaluator can reason only over existing structured metrics,
  sources, comparisons, warnings, coherence, limitations, and reviewed rules.
- A projection fingerprint binds finite application content; it is not an EDA
  native revision or immutability proof.
- No causal diagnosis becomes available merely because the taxonomy contains
  that class.
- No reviewed general teaching corpus or causal/hypothesis rule catalog exists
  yet.
- Numeric confidence is intentionally absent.
- Evidence references and policy state are process-local until durable storage,
  issuance, and recovery receive separate design.
- Phase 8C.1 creates no model capability, next measurement, operation authority,
  physical confirmation, EDA mutation, or hardware execution.
