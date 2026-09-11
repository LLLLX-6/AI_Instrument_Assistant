# Phase 8C.2 — Structured Model Publication Boundary

Status: **PHASE 8C.2A COMPLETE — architecture reviewed; Phase 8C.2B current and not started**

This ADR records the implemented deterministic Phase 8C.2A publication boundary
over the completed Phase 8C.1 claim policy. The implementation calls no
DeepSeek, LlmRuntime, AgentLoop, JLCEDA, Hardware, Tool, IPC, or external
runtime. Phase 8C.2B and real-model validation remain unauthorized and not
started.

## Implementation record

Phase 8C.2A now provides:

- immutable Host-owned `PublicationProjection`, request-local aliases and a
  complete `permission_content_id`;
- a minimal closed `aia-teaching-claim-candidate/v1` Schema shared by Python
  and TypeScript contract tests;
- an exact JSON parser at the protocol adapter boundary, including duplicate-key,
  size, count, unknown-field and full-input checks;
- a provider-neutral `EngineeringClaimGroundingGuard` which recomputes the
  Phase 8C.1 envelope and projection from current trusted context before
  resolving candidate aliases;
- immutable `GroundedPublicationPlan` values containing trusted slots and
  render atoms, never candidate-authored factual prose;
- the single `AIA_CANONICAL_EN_V1` renderer with source, quality, warning,
  sequential-coherence, snapshot-limitation, comparison status and exact-reason
  handling;
- fail-whole candidate handling, bounded deterministic fallback, one terminal
  fallback and a required final-Egress port;
- a thin TypeScript compatibility adapter proving canonical rendered output is
  checked by the existing production Phase 7C Egress Guard; and
- bounded audit records containing identities, decisions, counts and digests,
  but not raw rejected payloads.

Candidate binding fields remain untrusted claims. Current authority is always
reconstructed from the Host-owned context, envelope and typed goal. Projection,
permission, plan and candidate SHA-256 values remain content identities only.

## 1. Decision summary

Phase 8C.2 will use the model only as a bounded selector and ordering assistant.
The model may select a subset of exact `ALLOW` claim slots and order them. It
does not author the published wording, numeric values, source attribution,
comparison meaning, limitations, or warnings.

The approved publication flow is:

```text
immutable TeachingDiagnosisContext
  + exact AllowedClaimEnvelope
  + trusted typed TeachingGoal
        |
        v
PublicationAuthorityProjectionBuilder
  - resolves every permission against the exact context
  - assigns exact permission content identities
  - creates request-scoped opaque aliases
  - creates trusted renderer atoms and a minimal model view
        |
        v
bounded ModelSelectionProjection
        |
        v
one zero-Tool model request
        |
        v
raw response buffer
  -> raw-size limit
  -> Phase 7C Egress security precheck
  -> exact-one-JSON-object parser
  -> JSON Schema validation
        |
        v
StructuredClaimCandidateSet
        |
        v
EngineeringClaimGroundingGuard
  - exact request/context/envelope/goal/projection binding
  - exact permission resolution
  - ALLOW and publishable-kind checks
  - subject/support/obligation resolution
  - no strengthening
  - exact ComparisonStatus + ComparisonReason semantics
        |
        v
GroundedPublicationPlan
        |
        v
deterministic reviewed renderer
        |
        v
final Phase 7C Egress inspection
        |
        +-- SAFE -> publish deterministic text
        `-- UNSAFE -> bounded model-free failure notice

Any model, parse, binding, grounding, rendering, or Egress failure
        -> discard the whole model candidate
        -> build the Phase 8C.1 deterministic fallback plan
        -> validate obligations
        -> deterministic rendering
        -> final Egress
        -> publish only if safe
```

The candidate has no free-form prose field. The deterministic renderer is the
only component allowed to turn trusted evidence and exact claim permissions
into user-visible engineering language.

## 2. Trust and authority model

The trusted inputs are the immutable `TeachingDiagnosisContext`, the exact
`AllowedClaimEnvelope` produced from it, and a `TeachingGoal` supplied by the
trusted Host/application workflow. Before projection, the application must
recompute the finite context fingerprint, recompute or verify the envelope,
and require exact goal equality.

Everything returned by the model is untrusted, including JSON, identifiers,
ordering, whitespace, and apparent acknowledgements. Schema validity is not
trust. A content hash is not trust. A candidate may narrow an already-allowed
set by selection; it can never widen that set.

Neither projection nor publication objects may contain or create:

- Tool names, Tool arguments, or Tool results;
- `TrustedOperationScope` or invocation budget;
- Physical Policy state or `ProbeSetupConfirmation`;
- IPC operations or Hardware commands;
- EDA write/highlight commands;
- artifact-fetch capability;
- arbitrary source code or executable JavaScript.

## 3. Phase decomposition

### Phase 8C.2A — deterministic candidate, guard, and renderer

Implemented without a real model:

- the separate versioned projection/candidate JSON contract;
- trusted authority-projection and minimal model-projection builders;
- deterministic permission content identities and request-scoped aliases;
- strict parser and Schema validation;
- `EngineeringClaimGroundingGuard`;
- deterministic canonical renderer;
- obligation-aware deterministic fallback publication;
- scripted/fake model-port tests and architecture tests.

Phase 8C.2A uses recorded and synthetic evidence only. It has zero LLM requests
and zero external execution.

### Phase 8C.2B — bounded model adapter and publication composition

After 8C.2A review, integrate the frozen official DeepSeek LLM adapter through
`LlmRuntime.stream()` as one bounded request. Do not install AgentLoop,
ToolRuntime, AgentRegistry, SessionStore, or any Hardware plugin into this
dedicated model-call context. Buffer the complete response and pass it through
the 8C.2A boundary before publication.

Use a scripted adapter first. A real DeepSeek validation is a later, separately
authorized validation task and is not part of ordinary automated tests.

## 4. Separate protocol ownership

Phase 8C.2A introduces the separate namespace:

```text
protocols/teaching-claims/v1/
  README.md
  structured-claim-candidate-set.schema.json
  fixtures/
    valid/
    invalid/
```

The protocol identifier is
`aia-teaching-claim-candidate/v1`. JSON Schema is the wire-format single source
of truth for the cross-language shapes. Exact context/envelope/goal/projection
binding, alias-table ownership, one-attempt lifecycle, and trust of the
projection origin are semantic rules outside JSON Schema.

This namespace is additive. It must not modify:

- Evidence v1;
- AIA-JLCEDA v1;
- Hardware canonical schema;
- Harness-Hardware v1.

## 5. Permission identity strategy

Phase 8C.1 has unique claim slots, but `ClaimPermission` has no explicit stable
identifier. Phase 8C.2 therefore needs a deterministic
`permission_content_id` computed by the trusted projection builder from:

- the exact envelope ID and context fingerprint;
- typed goal;
- policy name and policy version;
- claim kind and claim form;
- complete canonical subject reference;
- decision and support basis;
- all ordered/canonical reason codes;
- all complete support references;
- every mandatory publication obligation;
- every obligation reference.

The identity is a SHA-256 content identity only. It is not authentication,
authorization, freshness, persistence, a signature, or provenance proof. Trust
still comes from the trusted application input and the exact structured
resolution performed in the current publication request.

The full `permission_content_id` remains inside the trusted authority
projection and audit record. The model sees only request-scoped aliases such as
`p001`, assigned from the envelope's canonical permission order. An alias is
meaningful only inside one exact `projection_id`; it is neither globally stable
nor a security token.

## 6. Publication authority projection

The trusted `PublicationAuthorityProjection` is a finite publication view, not
a new evidence source. It is built only after resolving every projected ALLOW
permission against the original `TeachingDiagnosisContext` and envelope. For
each permission it carries:

- permission content identity and request-scoped alias;
- the exact claim kind, form, subject, support basis, and reason codes;
- resolved support and obligation references;
- exact source/category/quality/availability metadata;
- exact comparison status and exact comparison reason where relevant;
- typed renderer atoms derived from trusted context values;
- mandatory obligation set;
- the canonical renderer profile/version capable of satisfying those
  obligations.

Renderer atoms are typed values, units, source categories, quality states,
warning/limitation codes and bounded display labels. They are not prewritten
model prose. The builder fails closed if a reference is unresolved, a renderer
atom cannot be represented, or the projection exceeds its bound. It never
silently truncates an authority projection.

If this projection later crosses a process boundary, its origin must be
protected by a separately reviewed trusted Host or authenticated transport.
Schema validation and content hashes alone do not establish trusted origin.
No such production transport is approved by this ADR.

## 7. Minimal model selection projection

The model receives only the information needed to select useful slots:

- protocol and projection versions;
- bounded request correlation reference;
- exact projection content identity;
- exact context fingerprint and envelope ID;
- exact typed `TeachingGoal`;
- candidate claim-count budget;
- only current concrete `ALLOW` permissions;
- for each slot: opaque permission alias, claim kind/form, subject category,
  metric when present, evidence source category, availability/quality class,
  exact comparison status/reason when present, and obligation-code names;
- a closed instruction that output must be one candidate JSON object.

It does not include:

- the entire evidence graph;
- provider document/object IDs;
- workflow authorization or physical confirmation;
- raw waveform samples or artifact contents;
- local paths, VISA resources, serials, secrets, SCPI, or runtime state;
- blocked permission aliases;
- free-form diagnostic or causal slots;
- renderer atoms not needed for selection.

Minimal bounded presentation labels may be included only when produced by a
trusted sanitizer, length limited, Egress prechecked, and explicitly
non-authoritative. Labels never resolve identity.

## 8. Structured candidate model

The v1 candidate is intentionally weaker than a normal structured answer. Its
conceptual fields are:

| Field | Meaning |
| --- | --- |
| `schema` | constant `aia-teaching-claim-candidate/v1` |
| `request_ref` | exact echo of the bounded request correlation value |
| `projection_id` | exact content identity of the model projection |
| `context_fingerprint` | exact Phase 8C.1 context content identity |
| `envelope_id` | exact Phase 8C.1 envelope content identity |
| `goal` | exact typed `TeachingGoal` |
| `claims` | ordered array of objects containing only `permission_ref` |

There is no claim text, numeric value, unit, source assertion, confidence,
reason override, warning acknowledgement, diagnostic field, Tool field, or
arbitrary metadata. `additionalProperties: false` and
`unevaluatedProperties: false` apply at every object boundary.

The candidate may select and order permissions only. All engineering semantics
come from the exact resolved permission and trusted renderer atoms.

## 9. Bounds

The initial reviewed limits are:

| Surface | Limit |
| --- | ---: |
| eligible ALLOW slots in one authority/model projection | 64 |
| selected candidate claims | 12 |
| raw model response | 16,384 UTF-8 bytes |
| request reference | 96 ASCII characters |
| optional sanitized display label | 96 Unicode scalar values |
| warnings/limitations carried per renderer plan | 16 each |
| final rendered answer | 16,384 characters, also subject to Egress |

If an exact authority projection exceeds its limit, model invocation is
skipped and the bounded deterministic fallback planner is used. It is not
silently truncated and still called complete.

Duplicate permission references are forbidden even if ordering differs.
Duplicate JSON keys are rejected before ordinary object mapping. The candidate
order is the primary-claim order; renderer-added mandatory clauses are attached
to the first affected claim and deterministically deduplicated.

## 10. Exact parsing boundary

The raw response pipeline is:

1. buffer provider chunks privately;
2. reject unsupported block types, including every Tool-call block;
3. count UTF-8 bytes and reject overflow without truncation;
4. apply the raw Egress security precheck;
5. require exactly one JSON object and full-input consumption;
6. reject Markdown fences, prefixes, suffixes, multiple JSON values, trailing
   prose, duplicate object keys, invalid encoding, or non-object roots;
7. validate the object against the exact v1 Schema;
8. create an immutable parsed candidate;
9. pass only the parsed candidate to engineering grounding.

There is no permissive extraction, regular-expression repair, coercion,
unknown-field removal, default insertion, enum normalization, or second model
request. Raw model output never reaches the user, Agent session history,
ordinary logs, or unrestricted persistence.

## 11. EngineeringClaimGroundingGuard

The new guard is deterministic and provider neutral. Its input is the trusted
authority projection plus the parsed candidate. It does not depend on Harness,
DeepSeek, EDA, Hardware, Tools, IPC, drivers, or the Phase 7C natural-language
parser.

For the whole candidate it validates, in order:

1. exact schema/projection version;
2. exact request reference, projection ID, context fingerprint, envelope ID,
   and typed goal;
3. candidate count and unique permission aliases;
4. alias resolution through the current request's immutable alias table;
5. exact permission-content identity and membership in the current envelope;
6. `decision == ALLOW`;
7. claim kind is one of the three Phase 8C.1 publishable kinds;
8. subject resolves against the exact context-bound authority projection;
9. all support and obligation references resolve and retain their categories;
10. source/category/quality/availability semantics match trusted renderer atoms;
11. comparison interpretation binds exact status plus exact reason;
12. the selected renderer profile can semantically satisfy every obligation;
13. no claim form can be rendered at a stronger semantic level;
14. the complete grounded plan remains within output bounds.

Success returns a `GroundedPublicationPlan` containing resolved trusted
permission objects and renderer atoms. It does not return model prose. Failure
returns category-only diagnostics and discards the whole candidate.

## 12. Publication obligations

Model acknowledgements are not proof that an obligation was met. In v1 the
candidate has no acknowledgement field.

Each reviewed renderer template declares a closed semantic-coverage set. The
guard requires every permission obligation to be covered by that template and
requires every obligation reference to resolve. During rendering:

- source attribution comes from the trusted evidence source;
- unavailable/degraded state is emitted from the trusted quality state;
- all material referenced warnings are emitted automatically;
- sequential coherence is preserved and simultaneous/atomic language is
  absent by construction;
- design observations are identified as observation identity only and never as
  proof of design immutability;
- tolerance-unspecified and compliance-undetermined clauses are emitted only
  for the exact supporting status/reason pair;
- comparison reason is always rendered from the trusted comparison atom.

If no reviewed template covers every obligation, grounding fails and the
candidate is discarded. The model cannot suppress a warning by omitting a
separate warning claim.

## 13. Deterministic renderer

The renderer consumes only `GroundedPublicationPlan` or the deterministic
fallback plan. It does not accept model text. It performs only:

- exact template selection by claim kind and claim form;
- deterministic bounded number and unit formatting from trusted typed values;
- reviewed source/quality/availability wording;
- mandatory warning, limitation, coherence, and observation-identity clauses;
- stable punctuation and ordering.

The initial locale/profile is one reviewed English profile,
`AIA_CANONICAL_EN_V1`. The model cannot select a locale or template variant.
Additional locales or variants require reviewed finite templates and semantic
equivalence tests; they are not arbitrary paraphrasing surfaces.

This means the model influences relevance and order, not engineering truth or
wording.

## 14. Exact comparison rendering

Comparison templates are keyed by the pair
`(ComparisonStatus, ComparisonReason)` and the exact `ClaimForm`.

- `INDETERMINATE / TOLERANCE_UNSPECIFIED` may render that no compliance result
  can be determined because an explicit tolerance is absent.
- Another indeterminate reason, including `MEASUREMENT_MISSING`, must render
  that exact reason and cannot use the missing-tolerance template.
- `MATCH` and `MISMATCH` wording is available only for exact reviewed reasons
  supported by the Phase 8C.1 permission.
- A deterministic difference may be rendered when its exact permission exists,
  but difference alone never becomes pass/fail, normal/faulty, or causal.

Reason replacement, fuzzy reason grouping, and numeric-closeness interpretation
are prohibited.

## 15. Fail-whole policy

Phase 8C.2 chooses **fail whole candidate**, not partial salvage. A single
unknown alias, duplicate claim, stale binding, unsupported kind, unresolved
reference, obligation failure, or semantic mismatch discards the complete
candidate.

Partial salvage would make the final answer depend on parser/validator error
position, could separate a claim from its mandatory warning, and would create a
hard-to-audit implicit repair policy. A deterministic fallback is simpler and
safer.

## 16. Deterministic fallback

The existing Phase 8C.1 `DeterministicFallback` remains the source of eligible
fallback permissions. Phase 8C.2 adds a bounded fallback planner and the same
reviewed renderer used for grounded candidates.

The fallback planner:

1. verifies the exact context/envelope/goal binding again;
2. takes only concrete ALLOW evidence, comparison, and limitation permissions;
3. prioritizes mandatory context limitations and material warnings;
4. selects a deterministic bounded evidence summary without severing any
   selected claim from its obligations;
5. emits no knowledge, inference, hypothesis, diagnosis, or proposal;
6. renders through the canonical profile;
7. passes final Egress before publication.

If no obligation-complete plan fits, publish only a constant bounded operational
notice that a grounded explanation could not be produced. That notice contains
no engineering assertion. It also passes final Egress. No model repair is
requested.

## 17. Phase 7C Egress compatibility

The current Phase 7C Egress Guard is suitable as a raw structured-output
**security precheck** because its purpose is disclosure safety: it blocks
credential material, absolute paths, full serials, VISA resources, raw command
shapes, waveform arrays, and oversized output. It is not a JSON parser and is
not engineering grounding.

Phase 8C.2B should add an explicit `MODEL_CANDIDATE_RAW` source category or a
narrow adapter that maps to an equivalent model-output source without changing
existing Phase 7C decisions. Raw candidate size is measured in UTF-8 bytes
before parse. The raw security precheck happens before any normal logging or
persistence.

After deterministic rendering, the final text must pass the ordinary final
Egress inspection. Egress SAFE never implies engineering grounding.

## 18. Phase 7C Grounding compatibility decision

The selected option is **B: keep the Phase 7C constrained-English Grounding
Guard unchanged and introduce an additive structured
`EngineeringClaimGroundingGuard` for Phase 8C**.

The existing Guard is correct for its bounded `TeachingEvidenceContext` and
English claim grammar, but it cannot authoritatively resolve Phase 8 design
facts, design targets, exact envelope permissions, or full comparison
references. Expanding it with labels or regexes would weaken the new boundary.

For Phase 8C publication, structured engineering grounding plus deterministic
rendering is authoritative, followed by final Egress. The Phase 7C Guard remains
authoritative and unchanged on the existing Phase 7C natural-language Agent
path. It may be used only as optional defense-in-depth for a compatible rendered
subset; it must not become a competing truth authority or a required gate that
misclassifies legitimate design/comparison templates.

## 19. Model execution boundary and AgentLoop decision

The frozen Harness baseline exposes `LlmRuntime.stream()` independently of
AgentLoop. Phase 8C.2B will reuse the reviewed official DeepSeek adapter and
LLM runtime at the exact frozen versions, but **will not use AgentLoop**.

Reasons:

- the task is one structured selection request, not a multi-turn agent loop;
- no Tool registry or Tool execution is needed;
- direct streaming accepts an explicit empty/omitted Tool set;
- complete local buffering can occur before any publication;
- there is no Agent session into which rejected raw output can be persisted;
- request count is directly bounded to one;
- no Agent retry, Tool retry, or follow-up behavior exists to contain.

The dedicated model context loads only the LLM runtime and reviewed DeepSeek
adapter. Any Tool-call, reasoning-text block outside the reviewed response
surface, multiple terminal responses, or abnormal stream sequence is rejected.
The exact frozen compatibility baseline remains commit
`d347e703908d0406b7a7ef80e3a0e594d86b2215` and package shape
`0.1.3-alpha.1`; no future-version compatibility is claimed.

Because the deterministic evidence policy is Python-centered while the
reviewed model runtime is TypeScript, the cross-language authority/model
projection contract must be explicit. A trusted production process bridge is
not currently approved. Phase 8C.2A can validate both language bindings over
shared fixtures; Phase 8C.2B must obtain separate review for the concrete
trusted Host composition before claiming production end-to-end publication.

## 20. Retry and failure policy

Maximum model attempts per publication request: **one**.

There is no retry for provider error, timeout, truncation, invalid JSON, schema
failure, stale binding, grounding failure, renderer failure, or Egress failure.
There is no model self-repair prompt. There is no Tool call, IPC replay,
measurement retry, hardware remeasurement, or EDA reread. Every failure moves
directly to deterministic fallback.

The model adapter uses a bounded timeout and cancellation signal. A late result
after timeout is discarded and cannot be published.

## 21. Bounded failure categories

Diagnostics contain only stable categories and bounded correlation metadata;
they never contain raw candidate text, secret/path fragments, stack traces, or
provider payloads.

Initial categories are:

- `PROJECTION_BINDING_INVALID`
- `PROJECTION_TOO_LARGE`
- `MODEL_REQUEST_FAILED`
- `MODEL_REQUEST_TIMEOUT`
- `MODEL_RESPONSE_EMPTY`
- `MODEL_OUTPUT_BLOCK_UNSUPPORTED`
- `RAW_OUTPUT_TOO_LARGE`
- `RAW_EGRESS_BLOCKED`
- `EXACT_JSON_OBJECT_REQUIRED`
- `DUPLICATE_JSON_KEY`
- `CANDIDATE_SCHEMA_INVALID`
- `CANDIDATE_BINDING_MISMATCH`
- `CLAIM_LIMIT_EXCEEDED`
- `DUPLICATE_PERMISSION_REFERENCE`
- `UNKNOWN_PERMISSION_REFERENCE`
- `PERMISSION_NOT_ALLOWED`
- `CLAIM_KIND_NOT_PUBLISHABLE`
- `SUBJECT_UNRESOLVED`
- `SUPPORT_REFERENCE_UNRESOLVED`
- `OBLIGATION_REFERENCE_UNRESOLVED`
- `PUBLICATION_OBLIGATION_UNSATISFIED`
- `SOURCE_ATTRIBUTION_MISMATCH`
- `COMPARISON_SEMANTICS_MISMATCH`
- `FORBIDDEN_STRENGTHENING`
- `RENDER_PLAN_INVALID`
- `FINAL_EGRESS_BLOCKED`
- `FALLBACK_UNAVAILABLE`
- `BOUNDED_INTERNAL_FAILURE`

## 22. Audit model

The bounded audit record may contain:

- request correlation reference;
- model provider/model identifiers from trusted configuration;
- request count and terminal outcome category;
- projection version and content identity;
- context fingerprint, envelope ID, typed goal;
- selected permission content identities after successful resolution;
- a digest and byte count of the raw response, but not raw response content;
- parse, grounding, renderer, fallback, and final-Egress status categories;
- renderer profile/version;
- published-result digest and character count;
- Tool, IPC, EDA, Hardware, and remeasurement counts, all required to be zero.

Audit hashes are correlation/content identities only. They are not proof that
an event was authorized, fresh, authentic, or persisted durably. Provider
internal telemetry is outside this bounded audit claim.

## 23. PWM positive test matrix

The initial deterministic PWM fixture contains the established design target
and separate instrument/software evidence, with no explicit tolerance.

Positive tests must prove:

1. a valid candidate selects bounded physical-frequency, software-duty,
   comparison, and limitation permissions;
2. candidate ordering is preserved for primary claims;
3. exact values and units come from renderer atoms, not candidate content;
4. instrument and software sources remain distinct;
5. `INDETERMINATE / TOLERANCE_UNSPECIFIED` renders the exact missing-tolerance
   limitation and no pass/fail conclusion;
6. degraded evidence automatically carries degraded state and all material
   warnings;
7. unavailable evidence renders unavailability and no borrowed value;
8. context/envelope/goal/projection bindings resolve exactly;
9. the deterministic fallback renders an obligation-complete bounded answer;
10. final Egress reports SAFE for the reviewed output;
11. model request count is zero under scripted 8C.2A and exactly one under
    scripted 8C.2B composition;
12. Tool, IPC, EDA, Hardware, and remeasurement counts remain zero.

## 24. Adversarial test matrix

The required adversarial scenarios are:

A. stale context fingerprint;
B. stale envelope ID;
C. wrong typed goal;
D. stale projection ID or request reference;
E. invented permission alias;
F. alias from another projection/envelope;
G. duplicate permission references;
H. attempted BLOCK/hypothesis/causal/general-knowledge/proposal permission;
I. attempted source misattribution through an unknown candidate field;
J. attempted false comparison status or reason through an unknown field;
K. degraded claim whose selected renderer profile cannot cover every warning;
L. unavailable claim whose template attempts to emit a value;
M. Markdown-fenced JSON;
N. two JSON objects, leading commentary, or trailing prose;
O. unknown properties, wrong schema/version, wrong enum, coercion attempt,
   duplicate JSON key, empty or over-limit claim list;
P. credential/path/VISA/SCPI/sample-array shapes or oversized raw output;
Q. unexpected Tool-call or unsupported stream block;
R. provider timeout/error/late result;
S. unsafe final deterministic rendering after otherwise valid grounding;
T. fallback renderer unable to satisfy an obligation or final Egress.

Tests I and J are expected to fail at Schema validation because v1 exposes no
source, status, reason, value, or prose field. Tests K and L exercise the guard
and template registry directly to prove that a future template regression
cannot bypass obligations.

Every negative test asserts one model attempt at most, no model repair, no
partial candidate publication, and zero Tool/IPC/EDA/Hardware side effects.

## 25. Automated validation plan

### Stage A — deterministic boundary only

- Python model/envelope/projection unit tests;
- Python and TypeScript shared Schema fixtures;
- strict parser tests, including duplicate-key and exact-one-object behavior;
- permission-identity canonicalization tests;
- alias scoping and stale-binding tests;
- Engineering Guard and renderer tests;
- obligation and fallback tests;
- Egress precheck/final-Egress composition tests with no LLM runtime;
- architecture dependency tests;
- frozen-schema semantic checks.

### Stage B — scripted/fake model integration

- frozen `LlmRuntime.stream()` with a scripted adapter;
- tools omitted/empty and Tool-call chunks rejected;
- one-request accounting and timeout/cancellation behavior;
- all positive/adversarial candidate streams;
- proof that rejected output never reaches a session or normal log;
- proof of zero AgentLoop, ToolRuntime, IPC, EDA, or Hardware dependency.

### Stage C — later real DeepSeek validation

Only after 8C.2A/8C.2B implementation and architecture review, run one
separately authorized bounded request with recorded/synthetic evidence. Record
whether the model returned a valid candidate or deterministic fallback was
used. Do not assert exact stochastic selection order as a safety property.

No Stage uses real JLCEDA or real Hardware.

## 26. Architecture and security tests

Architecture tests must prove:

- provider-neutral projection/guard/renderer code imports no Harness, DeepSeek,
  JLCEDA, VISA, SCPI, Rigol, IPC, Tool runtime, Driver, or Hardware service;
- model adapter imports no Hardware, EDA, authorization, or physical-policy
  implementation;
- only the adapter boundary imports official LLM runtime types;
- no AgentLoop, ToolRuntime, Tool schema, or Hardware plugin is registered in
  the Phase 8C.2 model context;
- candidate schemas contain no Tool/operation/confirmation fields and reject
  unknown properties;
- model output cannot supply renderer text, values, sources, reasons, or
  obligations;
- renderer reads only trusted grounded plans;
- raw output is not passed to logging/session/persistence callbacks;
- no arbitrary code evaluation or dynamic method dispatch exists.

Use schema compilation, import/dependency tests, AST/source-structure tests, and
behavior tests. Plain keyword grep is not the primary architecture control.

## 27. Pass criteria

Phase 8C.2 implementation can pass only when:

- all model candidates are valid exact v1 JSON or are discarded whole;
- every published engineering sentence originates from a resolved concrete
  ALLOW permission and reviewed renderer template;
- all bindings and references resolve against the exact current context;
- all mandatory obligations are semantically emitted;
- exact comparison status/reason semantics are preserved;
- no blocked claim kind can be selected or rendered;
- raw and final Egress gates both pass;
- all failures use deterministic fallback with no repair request;
- request count is at most one and all Tool/IPC/EDA/Hardware counts are zero;
- current Phase 7C behavior and frozen schemas remain unchanged;
- full repository regression, typecheck, builds, contract tests, architecture
  tests, and `git diff --check` pass.

## 28. Phase 8C.3 entry criteria

Phase 8C.3 may begin only after Phase 8C.2 is implemented, architecture
reviewed, committed, and passes the criteria above. In addition:

- `NEXT_MEASUREMENT_PROPOSAL` remains blocked throughout Phase 8C.2;
- no proposal field exists in the v1 candidate;
- proposal identity, unresolved-question binding, purpose allowlist, and
  non-executable semantics receive a separate design;
- accepting/displaying a proposal must still grant no operation scope,
  physical confirmation, Tool, IPC, or Hardware authority;
- any later execution returns to a separate trusted Host workflow with renewed
  authorization.

## 29. Compatibility findings

1. **AgentLoop is broader than required.** The frozen LLM runtime already
   exposes direct streaming, so AgentLoop would add session, loop, and Tool
   surfaces without benefit.
2. **Current Egress is reusable but needs a candidate source classification.**
   Its security shapes apply to raw JSON; its result does not prove parse or
   grounding validity.
3. **Current Phase 7C Grounding must not be widened into the structured guard.**
   It intentionally validates constrained English over `TeachingEvidenceContext`
   and lacks Phase 8C design/envelope authority.
4. **`ClaimPermission` lacks an explicit content ID.** Phase 8C.2 needs one
   derived from every permission semantic and envelope binding; it remains an
   identity, not authority.
5. **Current fallback is a permission projection, not rendered publication.**
   A bounded obligation-aware fallback planner and canonical renderer are
   needed without changing Phase 8C.1 semantics.
6. **Python/TypeScript composition is not yet a trusted production path.** The
   separate projection/candidate schema can prove shape compatibility, but a
   future concrete process boundary needs its own trusted-origin review.
7. **No reviewed multilingual renderer exists.** The initial finite renderer is
   constrained English; Chinese or other languages require separately reviewed
   templates rather than model paraphrasing.

These are implementation prerequisites or bounded limitations, not reasons to
change any frozen canonical evidence, EDA, or Hardware schema.

## 30. Bounded limitations

- The model only selects and orders exact slots; it does not create an original
  teaching explanation.
- The first renderer supports a finite English surface, not arbitrary natural
  language.
- Content fingerprints and IDs are process/content identities only.
- Alias maps and publication requests are process-local until durable storage
  receives separate design.
- Schema validation cannot prove trusted projection origin.
- The design supports only the three concrete Phase 8C.1 ALLOW claim kinds.
- No reviewed general-knowledge corpus, engineering-inference rule,
  hypothesis rule, causal rule, or next-measurement rule is enabled.
- No tolerance is invented; tolerance-unspecified remains indeterminate.
- No raw artifact/sample inspection exists.
- Direct frozen Harness compatibility is bounded to the reviewed package
  versions and exact API shape.
- A real DeepSeek result is stochastic supplementary evidence, never the sole
  safety proof.
- Phase 8C.2 grants no model, EDA, Hardware, Tool, or external-execution
  authorization by this architecture document alone.

## 31. Implemented Phase 8C.2A files

The implemented deterministic surface is:

```text
protocols/teaching-claims/v1/
  README.md
  structured-claim-candidate-set.schema.json
  fixtures/valid/
  fixtures/invalid/

src/ai_instrument_assistant/application/reasoning/publication/
  __init__.py
  models.py
  identity.py
  projection.py
  grounding.py
  renderer.py
  pipeline.py
  errors.py

src/ai_instrument_assistant/protocol/
  teaching_claims.py

extensions/deepseek-harness/src/publication/
  final-egress.ts
  index.ts

tests/architecture/
  test_phase8c2_publication_boundaries.py
tests/contract/teaching_claims_protocol/
  test_contracts.py
tests/unit/application/reasoning/publication/
  test_phase8c2a.py

extensions/deepseek-harness/tests/architecture/
  publication-boundary.test.ts
extensions/deepseek-harness/tests/contract/
  teaching-claims.test.ts
extensions/deepseek-harness/tests/unit/
  publication-final-egress.test.ts
```

The Host-owned authority and model-selection projections remain Python
application objects in 8C.2A. They were deliberately not made cross-language
wire contracts because the Python/TypeScript model composition boundary is
deferred to Phase 8C.2B review.

## 32. Real DeepSeek validation plan

A later real validation requires explicit authorization to send one bounded
model selection projection to DeepSeek. It will use recorded/synthetic PWM
evidence only, no JLCEDA connection and no hardware measurement. It will record:

- one request maximum;
- zero Tools, IPC, EDA, Hardware, and remeasurement;
- bounded projection metadata and exact frozen model adapter version;
- candidate accepted or discarded category;
- selected permission identities only after successful resolution;
- fallback use;
- final Grounding and Egress outcomes.

It will not persist raw rejected output, provider payloads, secrets, local
paths, or hidden reasoning. A real-model PASS means deterministic containment
worked for that bounded run; it does not prove universal model compliance.

## 33. Frozen non-goals

Phase 8C.2 must not add general electronics teaching from model memory,
case-specific inference, hypotheses, causal diagnosis, compliance invention,
next-measurement proposals, autonomous loops, EDA operations, measurements,
or artifact retrieval. It must not convert a model selection into execution
authority. It must not revise historical validation evidence.

## 34. Frozen implementation decisions

Phase 8C.2A implements the approved decisions:

1. permission-alias-only candidate shape;
2. 64 projected-slot, 12 selected-claim, and 16 KiB response bounds;
3. fail-whole behavior;
4. one canonical English renderer profile;
5. additive structured Grounding option B;
6. no LlmRuntime or AgentLoop in 8C.2A; direct frozen `LlmRuntime.stream()`
   remains the proposed 8C.2B model boundary;
7. the 8C.2A/8C.2B split;
8. separate `protocols/teaching-claims/v1` ownership;
9. the unresolved production Python/TypeScript trusted composition boundary as
   a bounded prerequisite rather than an implied completed feature.

## 35. Review disposition

The deterministic implementation, protocol, tests and documentation passed
architecture review and are complete for Phase 8C.2A. Phase 8C.2B is CURRENT
but NOT STARTED. No model adapter, cross-language model transport, external
request, EDA access, or Hardware access was created by Phase 8C.2A.

## 36. Phase 8C.2A validation record

The closeout validation used only local deterministic tests, fakes, static
checks, typechecks, and production builds. It made no model, JLCEDA, instrument,
Tool, IPC, or other external request.

- Phase 8C.2A targeted Python: 26 passed;
- Phase 8C.2A TypeScript contract/unit/architecture: 3 passed;
- supporting Phase 8C.1 and Phase 8B/Evidence/architecture selection: 112
  passed;
- Phase 7C Egress/Grounding compatibility selection: 6 passed;
- full Python: 517 passed;
- JLCEDA TypeScript: 84 passed, strict typecheck and production build passed;
- Harness unit/agent/Fake-E2E: 210 passed, strict typecheck and production
  build passed;
- unified entry: passed with exit code zero;
- Context Pack repository-relative link validation: passed;
- frozen Evidence v1, AIA-JLCEDA v1, and Hardware canonical schema paths had no
  semantic diff;
- `git diff --check`: passed.

Generated build artifacts remain ignored and are not Phase 8C.2A source. No
secret, real resource identifier, raw provider payload, raw waveform, model
output, or local host path is part of this implementation.
