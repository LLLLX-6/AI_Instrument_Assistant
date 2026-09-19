# AI Instrument Assistant — Project Baseline

Baseline date: 2026-09-12

Committed implementation baseline before Phase 8C.2B:
`c5866e2`

This document is a concise current-state map. It does not replace canonical
schemas, accepted ADRs, implementation, tests, or detailed validation records.

## 1. Purpose

AI Instrument Assistant is a Python-centered, teaching-oriented electronics
Agent system. Its core purpose is to combine design-side EDA evidence with real
hardware measurement evidence for safe, traceable, grounded teaching and
eventual diagnosis.

The intended long-term loop is design -> test -> analysis -> diagnosis ->
design feedback. The repository has established the bounded design, hardware,
Agent-governance, and deterministic evidence foundations for that direction,
including one reviewed real EDA-plus-hardware validation. It has not completed
arbitrary autonomous or causal diagnosis.

## 2. Architectural Style

- Modular monolith with explicit subsystem boundaries.
- Ports and adapters around EDA, instrument, artifact, model, and transport
  integrations.
- Provider-neutral immutable domain models.
- Application services orchestrate use cases through ports.
- Vendor protocols, SDKs, drivers, and runtimes stay at the edges.
- Deterministic authorization, physical safety, evidence, grounding, egress,
  and failure boundaries surround model-controlled execution.
- Versioned JSON Schema is the cross-language wire authority where a canonical
  wire contract is defined.

## 3. Main Subsystem Map

```text
User / trusted host workflow
  -> Agent
  -> TrustedOperationScope + Physical Policy
  -> five semantic Hardware Tools
  -> application services
  -> provider-neutral ports
  -> drivers / adapters
  -> external EDA, model, and instrument systems
```

### EDA side

```text
JLCEDA official extension (TypeScript)
  -> finite transport DTO
  -> aia-jlceda/v1 authenticated localhost protocol
  -> Python JLCEDA remote adapter / mapper
  -> provider-neutral EDAInterface and EDA domain
```

The separately authenticated `aia-interactive/v1` connection links the
JLCEDA official-Dialog companion to the authoritative Python Application Host.
Its configurable default is `127.0.0.1:49626`; 49624 remains provider-only and
49625 remains Hardware-only. The frontend submits bounded commands and exact
design-selection Challenge answers but creates no trusted decision or execution
authority.
The Phase 8.5B.1 production composition routes `design.observe` through an
async application adapter and provider-neutral `EDAInterface` to the separate
AIA-JLCEDA v1 gateway. Remote EDA I/O never holds the Host mutation lock; a
generation, revision, workflow, or request change discards the returning result
instead of overwriting newer Host state.

The first real Phase 8.5B interaction smoke remains historical NOT PASS even
though it proved both authenticated connections and two real Host-side
observations. The approved offline coordination repair keeps one inbound
consumer while
servicing authoritative snapshot requests independently of a pending async EDA
command. The JLCEDA client has an explicit synchronization state, and selection
callbacks, debounce work, waiters, and connections are generation-bound. A
separately authorized Attempt 2 proved that one explicit Status request reached
Python and one reply was sent, but successful TypeScript client completion was
not observed. Attempt 2 is NOT PASS.
The offline client-completion repair makes the explicit waiter
single-session/single-pending, completes it before non-authoritative snapshot
observers, and separates transport, validation, session, waiter, and
presentation diagnostics. Its offline architecture review passed. Separately
authorized Attempt 3 used v0.2.17 and stopped at Gate A: one initial snapshot
was sent, but the explicit Status action produced zero server-side snapshot
requests and replies. Phase 8.5B remains real-runtime incomplete, and no
further real retry is authorized by that record.

Bounded follow-up diagnostics established the root cause: exported JLCEDA menu
functions may execute in a separate VM/module context, so module-local activation
state is not a valid menu ownership mechanism. The official private
`SYS_MessageBus` successfully crossed that boundary to the connected
activation-owned Runtime. The uncommitted 0.2.23 repair routes a closed set of
runtime-dependent menu actions through one private command bridge. Service
registration is restricted to the connected owner, and offline production
Status plus design-observe loopbacks pass. Attempt 4 preserved that success but
ended NOT PASS at selection observation. Later Provider-context diagnostics
proved `getAllSelectedPrimitives()` succeeds for stable selection and that
ID-based reconstruction is lossy (two selected IDs resolved to one primitive).
The uncommitted 0.2.26 repair therefore retains the canonical object read,
removes the competing presentation-only read at the debounce boundary, and
allows at most one bounded read-only retry after an event-loop stabilization
turn. Phase 8.5B is **CLOSED FOR NOW / LIMITED INTEGRATION**. Reliable
automatic current-selection capture remains host-state-sensitive in the
reviewed JLCEDA 3.x runtime, so it no longer blocks the product roadmap. No
further real run is authorized under this disposition.

The retained integration capabilities are extension activation, Provider and
Interactive connections, ApplicationHost integration, the private cross-VM
MessageBus command bridge, Status, manual Refresh, and read-only EDA access.
Automatic current-selection capture, typed candidate binding sourced from that
UI capture, trusted design selection that depends on it, and automatic
`ProbeTarget` derivation from it are deferred. They may be reconsidered only
through a later reviewed product requirement and a demonstrably more reliable
integration mechanism.

Phase 8.5B production authority is deliberately split by runtime. Python
retains the full typed design-selection candidate binding and delegates an
exact validated choice to its existing trusted selection factory. Operation
Scope and physical-confirmation issuance stay in the Harness TypeScript
runtime and are deferred to Phase 8.5C; JLCEDA does not answer those Challenges.

Only the JLCEDA API adapter may touch official `eda.*` runtime objects. The
integration exposes read-only document/selection operations and a guarded view
highlight operation. It has no arbitrary JavaScript execution, raw method
dispatch, direct VISA access, or EDA design mutation. Provider acceptance of a
highlight remains distinct from verified visual application.

When a provider returns multiple objects without documented primary semantics,
the provider observation remains unchanged and ambiguous. Phase 8B.2 adds a
separate application-level trusted Host/user decision bound to the exact
workflow, request, document, snapshot, observation time, and candidate-set
fingerprint. It may select only an already-observed bounded candidate. It does
not populate provider `primary_object`, authorize execution, or create physical
confirmation.

### Hardware side

```text
HardwareToolRuntime
  -> MeasurementService
  -> OscilloscopeInterface
  -> DS1102Z-E Driver
  -> SCPI session
  -> VISA transport
```

The public surface is semantic and bounded. Waveforms remain behind opaque
`ArtifactReference` values; full sample arrays do not cross the Tool boundary.

### Evidence side

```text
Evidence v1
  -> immutable EngineeringEvidenceContext
  -> deterministic comparator
  -> EngineeringEvidenceWorkflow
  -> evidence-only TeachingDiagnosisContext
```

The Phase 8B.1 workflow validates design/target identity, establishes trusted
cross-reference evidence, selects matching measurement evidence, compares it
with explicit tolerance semantics, assembles the context, and projects the
teaching view. It creates no diagnosis, inference, Tool call, operation scope,
or physical confirmation.

### Reasoning-policy side

```text
immutable TeachingDiagnosisContext + trusted typed TeachingGoal
  -> deterministic InferenceSufficiencyEvaluator
  -> exact AllowedClaimEnvelope slots
  -> evidence/comparison/limitation-only fallback structure
```

Phase 8C.1 allows only exact evidence restatements, existing deterministic
comparison statements, and limitations. Knowledge-dependent education,
engineering inference, hypothesis, causal diagnosis, and next-measurement
proposals remain blocked. An ALLOW permission is necessary but not sufficient
for publication: later candidate validation must also resolve references,
satisfy every obligation without strengthening, and pass Grounding and final
Egress. Phase 8C.2A now implements that deterministic publication boundary. Its
minimal candidate contains only Host-binding claims and ordered Host-owned
permission aliases; it contains no factual prose, numeric values, or Tool/action
fields. The deterministic renderer is the only factual publication source.
Phase 8C.2B completes the one-shot model boundary with a provider-neutral
runtime port, bounded private process bridge, zero-Tool frozen DeepSeek route,
strict stream collection, raw Egress, strict candidate validation,
deterministic fallback/rendering, and independent final Egress. One separately
authorized real request passed approved safety Case B: its Schema-invalid
candidate was discarded and deterministic fallback was safely published. A
Schema-valid real-model happy path was not observed.

## 4. Canonical Contracts

- [`protocols/hardware/v1/hardware-tool.schema.json`](../../protocols/hardware/v1/hardware-tool.schema.json)
  is the canonical Hardware Tool wire schema.
- [`protocols/evidence/v1/`](../../protocols/evidence/v1/README.md) is the
  canonical cross-language Evidence v1 wire contract.
- [`protocols/harness-hardware/v1/`](../../protocols/harness-hardware/v1/README.md)
  defines the independent authenticated Harness-to-Python IPC contract.
- [`protocols/jlceda/v1/`](../../protocols/jlceda/v1/README.md) defines the
  independent JLCEDA integration wire contract.
- [`protocols/interactive/v1/`](../../protocols/interactive/v1/README.md)
  defines the independent unprivileged frontend/Host contract.
- [`protocols/teaching-claims/v1/`](../../protocols/teaching-claims/v1/README.md)
  defines the minimal Phase 8C.2A structured candidate wire contract.
- [`protocols/harness-publication-bridge/v1/`](../../protocols/harness-publication-bridge/v1/README.md)
  is the private integration-only Phase 8C.2B process bridge. Its receipts are
  transport claims to validate, never evidence, authorization, or engineering
  truth.

JSON Schema governs individual wire-format structure. Cross-message sequence,
authentication, correlation, nonce freshness, replay, session ownership, and
delivery certainty are separate protocol-state semantics; Schema does not
pretend to enforce them.

## 5. Frozen External Baselines

The only reviewed DeepSeek Harness source baseline is:

- commit `d347e703908d0406b7a7ef80e3a0e594d86b2215`;
- reviewed Harness package shape `0.1.3-alpha.1`;
- compatibility policy: exact reviewed shape only.

No compatibility with later Harness commits or package versions is implied.
The observed npm package noted in ADR-0004 is not an accepted substitute.

The JLCEDA extension currently pins pro-api-sdk `1.6.17`,
`@jlceda/pro-api-types` `0.4.14`, and EDA engine compatibility `^3.2.0`.
These pins describe the reviewed build/runtime boundary, not a guarantee for
future provider API behavior.

## 6. Current Validated Hardware

The current validated instrument is the Rigol DS1102Z-E. Real validation
observed firmware `00.06.03.SP2`.

Claims are bounded to the recorded workflows: the current device, safe
low-voltage setups, the tested semantic operations, and the documented capture
and analysis modes. The records do not establish industrial-grade accuracy,
arbitrary firmware compatibility, all channels/modes, mains/high-voltage
safety, atomic capture, or support for other instrument families.

## 7. Proven Real Path

The project has validated this bounded path:

```text
real DeepSeek
  -> official frozen Harness AgentLoop
  -> trusted operation scope
  -> physical policy
  -> governed semantic Tool
  -> authenticated localhost IPC
  -> real DS1102Z-E
  -> canonical evidence / TeachingEvidenceContext
  -> Egress Guard
  -> Grounding Guard
  -> guarded grounded output or deterministic grounded fallback
```

Phase 8B.3 additionally validated this bounded model-free evidence path:

```text
real read-only JLCEDA observation
  + trusted design disambiguation
  + separately trusted physical confirmation and operation scope
  + real DS1102Z-E evidence
  -> deterministic EngineeringEvidenceWorkflow
```

This proves deterministic containment for the recorded real scenarios. It does
not prove arbitrary autonomous diagnosis, unconstrained natural-language
grounding, design immutability, or durable production authorization.

Phase 8C.2B additionally validated this bounded publication path:

```text
recorded/synthetic TeachingDiagnosisContext
  -> deterministic claim envelope and projection
  -> one real DeepSeek request with zero Tools
  -> invalid candidate discarded
  -> deterministic grounded fallback and canonical renderer
  -> independent final Egress
```

This is real-model safety integration PASS, not evidence of a valid-candidate
happy path.

RE-001D-Lite additionally completed the bounded current-core conversational
proof:

```text
natural-language experiment request
  -> bounded intent and trusted physical confirmation
  -> four one-shot governed DS1102Z-E measurements
  -> strict canonical mapping and deterministic analysis
  -> provenance-separated teaching evidence
  -> one DeepSeek structured candidate
  -> deterministic grounded fallback and safe final Egress
```

The run preserved unexpected real measurements instead of rewriting them and
created no causal diagnosis. It proves governed conversational experimental
data flow, not RC-filter physical performance. The overall RE-001 status is
**CORE E2E PROOF COMPLETE**.

The current-output RE-001D plan declares no expected-frequency target: the
reviewed request names none, `requested_frequency_hz` is null, and the
frequency-relative-deviation metric is omitted from analysis and publication
unless an experiment plan explicitly declares a target (RE-001B 100 Hz point).

The bounded REAL Rigol interactive Web validation then proved the same
governed path against the real DS1102Z-E: trusted confirmation, four
one-shot scopes, four ordered authenticated instrument measurements with
`source = "instrument"`, targetless semantics preserved (no deviation
metric published), deterministic gain analysis, and safe grounded
publication. Recorded in
[RE-001D Real Rigol Interactive Web E2E](../validation/re001d-real-rigol-web-e2e.md).
The earlier approximately 10x Vpp discrepancy was traced to physical probe
attenuation/configuration and disappeared after physical correction; no
software compensation was added.

## 8. Current Limitations

- Harness compatibility is proven only for the frozen reviewed commit/package
  shape above.
- JLCEDA 3.x current UI-selection capture remains host-state-sensitive despite
  the bounded stabilization repair. It is not a source of automatic candidate
  binding, trusted design selection, or `ProbeTarget` derivation in the current
  limited integration.
- The `TrustedOperationScope` invocation-budget ledger is process-local.
- Production dynamic scope issuance, persistence, and recovery are incomplete.
- In-memory artifact references are scoped to the backend lifetime and are not
  durable storage.
- Grounding validates a constrained English claim surface; ambiguous or
  unrecognized claims fail closed.
- Hardware validation is bounded to the current DS1102Z-E workflows.
- Phase 8B.3 completed one bounded real read-only JLCEDA plus real DS1102Z-E
  validation. Its snapshot is observation identity only; `VERIFIED_LINK` does
  not prove design immutability.
- Trusted design disambiguation remains distinct from provider primary
  selection and from physical probe confirmation.
- The Phase 8B.3 authorization was validation-only and is not durable
  production authorization.
- Without explicit tolerance, the validated comparisons remain
  `INDETERMINATE / TOLERANCE_UNSPECIFIED`.
- Causal diagnosis is not implemented.
- Candidate next measurements remain empty/deferred.
- Phase 8C.1 SHA-256 fingerprints, envelope IDs, and comparison references are
  deterministic content identities only. They provide no authentication,
  authorization, freshness, persistence, signature, trust, or provenance proof.
- JLCEDA highlight submission can be accepted without programmatic proof of
  the exact visible effect.
- The Phase 8C.2B private stdio bridge is not authentication, its invocation
  budget is process-local, and its Node child is not OS-sandboxed.
- Phase 8C.2B did not observe a Schema-valid real-model candidate. It proved
  safe rejection and deterministic fallback instead.
- Phase 8 is complete without engineering inference, hypothesis, causal
  diagnosis, next-measurement proposals, or autonomous experimentation.
- RE-001 does not yet include reliable native JLCEDA selection, a successful
  positive Yuanlitu provider runtime validation, SimulIDE integration,
  automatic signal-generator control, frequency sweep or cutoff search, full
  RC physical validation, report export, or generalized diagnosis. These are
  deferred and do not invalidate the bounded core E2E proof.

## 9. Historical Validation Policy

Historical NOT PASS records remain historical. Later repairs or PASS results
must create new records and must not rewrite earlier failed runs into PASS.
Discarded model output, lost measurements, unreported provider outcomes, and
unknown execution counts must not be reconstructed.

The authoritative Phase 7 ledger is summarized in the
[Phase 7C closeout](../agent/phase7c-closeout.md).

## 10. Architecture Enforcement

Existing AST/import/module-boundary tests already enforce the relevant
dependency directions and authority separation. TypeScript architecture tests
use structural/source analysis for static allowlists and dangerous API rules.
Canonical contract tests validate shared fixtures in both languages, and
integration tests assert the safety ordering around Tool execution.

No additional documentation-only keyword test is justified by this context
pack. New enforcement should use AST, import graphs, module boundaries, schema
compilation, or behavior tests rather than brittle prose searches.

## 11. Detailed References

- [Phase 7C closeout](../agent/phase7c-closeout.md)
- [Phase 7C.4F final real validation](../agent/phase7c4f-final-real-grounded-validation.md)
- [Phase 8A.1 architecture](phase8a1-unified-engineering-evidence.md)
- [Phase 8A.2 architecture](phase8a2-engineering-evidence-core.md)
- [Phase 8B.1 workflow](phase8b1-evidence-workflow.md)
- [Phase 8B.2 real JLCEDA and recorded Hardware workflow](phase8b2-real-jlceda-recorded-hardware-workflow.md)
- [Phase 8B.2A trusted selection disambiguation](phase8b2a-trusted-design-selection-disambiguation.md)
- [Phase 8B.3 real EDA and real hardware workflow](phase8b3-real-eda-real-hardware-workflow.md)
- [Phase 8B.3 real validation attempt 1](../validation/phase8b3-real-validation-attempt-1.md)
- [Phase 8B.3 real validation attempt 2](../validation/phase8b3-real-validation-attempt-2.md)
- [Phase 8C.1 inference sufficiency policy](phase8c1-inference-sufficiency-teaching-policy.md)
- [Phase 8C.2B one-shot model integration](phase8c2b-deepseek-structured-candidate-integration.md)
- [Phase 8C.2B bounded real validation](../validation/phase8c2b-real-deepseek-validation.md)
- [Phase 8.5B runtime coordination repair](phase8_5b2-interactive-runtime-coordination-repair.md)
- [Phase 8.5B real JLCEDA smoke Attempt 2](../validation/phase8_5b-real-jlceda-design-smoke-attempt-2.md)
- [Phase 8.5B client completion repair](phase8_5b3-client-completion-boundary-repair.md)
- [Phase 8.5B menu runtime bridge](phase8_5b4-jlceda-menu-runtime-bridge.md)
- [Phase 8.5B selection stabilization repair](phase8_5b5-selection-stabilization-repair.md)
- [Phase 8.5B real JLCEDA smoke Attempt 4](../validation/phase8_5b-real-jlceda-design-smoke-attempt-4.md)
- [Phase 8 closeout](phase8-evidence-grounded-teaching-closeout.md)
- [Harness compatibility](../integrations/deepseek-harness-phase7a-compatibility.md)
- [Harness hardware adapter ADR](../adr/0004-deepseek-harness-hardware-adapter.md)
- [JLCEDA implementation constraints](jlceda-v0.2-implementation-constraints.md)
- [JLCEDA protocol state machine](aia-jlceda-v1-state-machine.md)
- [JLCEDA highlight findings](../compatibility/jlceda-phase5b4-highlight-findings.md)
- [Physical confirmation workflow binding](physical-confirmation-workflow-binding.md)
- [RE-001 experiment status](../experiments/re-001-rc-low-pass.md)
- [RE-001D-Lite final real conversational E2E](../validation/re001d-lite-final-real-conversational-e2e.md)
- [RE-001D Real Rigol interactive Web E2E](../validation/re001d-real-rigol-web-e2e.md)

## 12. Known Documentation Drift

Some point-in-time documents retain their historical status text. In
particular, the root `README.md` still describes Phase 5B.2b; the JLCEDA
extension README still describes Phase 5B.3b and says remote highlight is
disabled; and the Phase 8A.1, 8A.2, and 8B.1 documents retain pre-closeout
status headers. Use current code, canonical schemas, accepted closeouts, Git
history, tests, and `PHASE_STATUS.md` for current phase status. Do not rewrite
historical validation evidence merely to make the wording look current.

## 13. Physical Confirmation Workflow Binding Remediation

`ProbeSetupConfirmation.scope` carries both `requestCorrelationId` and
`workflowId`. The Physical Policy context now carries trusted workflow identity
and independently requires its workflow to equal the confirmation workflow for
REAL physical measurements. A mismatch requires a new confirmation and reaches
neither IPC nor hardware.

Operation Scope continues to validate its own workflow independently; neither
gate substitutes for the other. The repair is implemented, regression
validated, and architecture reviewed. It does not reinterpret prior bounded
real validation runs.
