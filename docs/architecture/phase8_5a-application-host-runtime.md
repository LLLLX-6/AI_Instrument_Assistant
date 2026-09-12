# Phase 8.5A — Application Host & Runtime Lifecycle

Status: **COMPLETE**
Date: 2026-09-12
Validation mode: **offline fakes only; architecture and implementation approved**

## 1. Scope and outcome

Phase 8.5A implements the local application foundation approved by the Phase
8.5 architecture. It adds one authoritative Python `ApplicationHost`, immutable
session/workflow values, explicit state transitions, Host-owned Challenges, a
bounded frontend protocol, fake frontend integration, lifecycle ports, and a
platform-adaptable bootstrap seam.

This phase adds no permanent JLCEDA or Harness UI and performs no real EDA,
instrument, VISA, Hardware IPC, or model action. It does not add an
unprivileged execute command.

## 2. Host authority and layering

`ApplicationHost` is the sole interactive aggregate. It owns the application
generation, workflow repository, monotonic workflow revisions, connection
generations, pending/consumed/withdrawn Challenges, retained event cursor,
bounded audit records, safe status state, and a lifecycle port for owned
runtimes.

Existing trusted logic remains behind inward ports. A validated frontend answer
can only request that a trusted issuer create a design decision, operation
authorization, or physical confirmation. The frontend cannot construct those
objects. Driver, VISA, SCPI, JLCEDA SDK, Harness browser SDK, Hardware IPC, and
DeepSeek imports are forbidden from the interactive application package.

The Host stores bounded references to evidence/publication state; it does not
copy evidence, comparator, policy, Grounding, renderer, or Egress logic.

## 3. Controlled state

`ApplicationSession` is immutable and carries a Host-generated UUID generation,
start time, and controlled Host state. A new Host instance creates a new
generation and cannot resolve Challenges from an earlier instance. Host
shutdown first marks the session stopping, withdraws all Challenges, disconnects
frontends, then stops the injected lifecycle owner. Repeated shutdown is
idempotent.

`WorkflowSession` is the authoritative immutable aggregate. It carries:

- workflow identity, revision, request correlation, and optional Harness
  conversation reference;
- design observation and candidate-set content identities;
- trusted design-decision and probe-target references;
- a content-identified bounded operation plan;
- Challenge references, scope reference, and remaining budget metadata;
- physical-confirmation, delivery, evidence, and publication references.

All sensitive transitions use expected-revision compare-and-set under the Host
lock. Stale or concurrent answers fail closed rather than merge.

The explicit finite state set is:

```text
IDLE -> OBSERVING_DESIGN -> DESIGN_CONTEXT_READY
  -> WAITING_FOR_DESIGN_SELECTION -> TARGET_RESOLVED
  -> OPERATION_PREPARED -> WAITING_FOR_OPERATION_AUTHORIZATION
  -> WAITING_FOR_PHYSICAL_CONFIRMATION -> READY_TO_EXECUTE
  -> CONNECTING_INSTRUMENT -> MEASURING -> ANALYZING
  -> BUILDING_EVIDENCE -> GENERATING_TEACHING_RESPONSE -> COMPLETE
```

Reviewed optional transitions support unambiguous selection and non-physical
paths. Every nonterminal state may fail or cancel. Terminal states cannot
transition. A state name grants no Scope, Physical Policy permission, IPC, or
execution authority.

## 4. Challenges and trust conversion

Each one-time Challenge binds:

- application generation, workflow/revision, request correlation;
- challenge ID, kind, allowed frontend kind, issuance/expiry, and random nonce;
- exact design candidate set, operation plan/channel/budgets, or physical setup
  target/channel/voltage/statements as appropriate.

The accepted path is active authenticated connection, bounded wire validation,
Host-owned challenge/workflow lookup, frontend-kind and generation checks,
exact revision, expiry, nonce and binding checks, atomic consumption, then an
inward trusted-issuer call and transition commit.

Duplicate, expired, wrong-frontend, wrong-generation, wrong-workflow,
wrong-revision, stale candidate, changed target/plan/channel, and replayed nonce
answers are rejected. Design refresh or operation-plan replacement withdraws
dependent Challenges and clears dependent authorization/confirmation refs.
Rejected answers produce zero issuer call, IPC, hardware action, and budget
consumption.

## 5. Commands, events, status, reconnect, and cancellation

Provider-neutral typed command values cover workflow start, design observation,
design answer, plan preparation, operation authorization answer, physical setup
answer, target highlight request, cancellation, and teaching publication
request. They accept no raw SCPI, arbitrary Tool name, EDA method, model prompt,
or trusted object. Execution remains internal orchestration.

Typed events carry Host event ID, generation, optional workflow/revision,
correlation, timestamp, event type, and a bounded safe payload. Event order is a
delivery fact, not engineering evidence or authority.

Reconnect creates a fresh connection/session generation. Subscription returns
the authoritative snapshot before later events. Retained cursors resume
delivery; future, negative, or pruned cursors fail closed. Reconnect does not
recreate consumed Challenges, nonces, Scope, budget, confirmation, or trusted
selection state.

Cancellation atomically withdraws pending Challenges and enters `CANCELLED`.
The Phase 8.5A Host has no execution dispatcher, so cancellation before dispatch
has zero IPC. Existing Phase 7 delivery semantics remain authoritative for
future post-dispatch cancellation: no refund, replay, or remeasurement.

`ProductStatus` is a field allowlist. Stable product error codes map to fixed,
bounded messages. It excludes ports, PIDs, paths, VISA resources, SCPI, serials,
credentials, provider payloads, model candidates, and waveform data.

## 6. `aia-interactive/v1`

The additive frontend contract lives under `protocols/interactive/v1`. JSON
Schema is the wire-shape authority; the protocol README separately defines
connection/session/challenge/cursor semantics that schemas cannot prove.

The contract provides version negotiation, session metadata, bounded commands,
Challenges and answers, snapshots, events, status, cancellation, and cursors.
Unknown fields fail closed. String and array sizes are bounded, and the gateway
binding limits serialized messages to 65,536 UTF-8 bytes. Shared Python and
TypeScript tests consume the same valid and invalid fixtures.

Authentication only permits a frontend to submit allowed messages. It never
grants a trusted design decision, operation Scope, physical confirmation, or
execution. Session messages must match both the active session ID and
application generation.

The Host-side gateway implemented here is a schema-bound handler seam, not a
real WebSocket server. Its production configuration is limited to explicit
`127.0.0.1:49624/interactive/v1`, preserving the existing 49624 ownership and
path-multiplexing decision behind an adapter seam.

## 7. Runtime and Windows seams

`LifecycleManager` manages registered runtimes through provider-neutral async
ports. It supports readiness timeout, task cancellation cleanup, crash status,
idempotent stop, reverse-order shutdown, and owned-child containment. Intended
lifetimes are:

- JLCEDA and interactive gateways: Host lifetime;
- Hardware backend: on demand;
- VISA session, DeepSeek executor, and final Egress executor: one attempt.

The containment port is suitable for a future Windows Job Object or equivalent
explicit owned-process handle. No shell spawn, POSIX-signal assumption, or
kill-by-port behavior exists.

`ApplicationBootstrap` is the non-CLI launcher/application service seam. A
platform adapter may implement the single-instance claim. A compatible running
Host is reused; incompatible or occupied endpoints fail closed. The bootstrap
never terminates an unknown process and releases its owned claim if Host startup
fails.

## 8. Test-first evidence

The Red run was captured before production modules/schemas existed:

- four interactive application test modules failed import with
  `ModuleNotFoundError`;
- the runtime lifecycle test failed import with `ModuleNotFoundError`;
- three contract test cases failed because no interactive Schema files existed.

The Green suites cover state/CAS, Challenge validation/replay/staleness,
snapshot/cursor/reconnect, cancellation, safe status/errors, lifecycle and
orphan cleanup, bootstrap/single-instance outcomes, gateway constraints, fake
Harness/JLCEDA clients, shared Python/TypeScript fixtures, and AST/hash-based
architecture boundaries.

## 9. Compatibility and frozen contracts

Phase 8.5A is additive. It makes no semantic change to Evidence v1,
AIA-JLCEDA v1, Hardware canonical, Harness-Hardware v1, teaching-claims/v1, or
harness-publication-bridge/v1. Architecture tests pin representative frozen
schema digests and prevent production frontend implementation in this phase.

## 10. Bounded limitations and next entry

- The Host, protocol handler, bootstrap, lifecycle ports, and fakes are
  implemented; no permanent product UI or real socket listener is present.
- Runtime ports do not yet contain production subprocess, Windows Job Object,
  named-object, or packaging adapters.
- Workflow/event repositories, Challenge replay state, authorization metadata,
  and audit are process-local and non-durable.
- Host restart intentionally invalidates ephemeral authority; durable recovery
  design is deferred.
- Event retention is bounded in memory; a cursor older than that window must
  resubscribe from a fresh snapshot.
- No execution orchestration is exposed in Phase 8.5A; existing Phase 7/8
  runtime and evidence controls remain separate and unchanged.

Phase 8.5B may start only after this implementation is reviewed and committed,
the real JLCEDA interaction API surface is rechecked against the pinned SDK,
the 49624 path-multiplexing seam is proven in a bounded compatibility spike,
and the Host Challenge/status contracts required by the design-side UI remain
stable. Phase 8.5B must not move trust or execution authority into the plugin.
