# AI Instrument Assistant — Project Baseline

Baseline date: 2026-09-10

Repository baseline: `76502f9ecd13ea971803b07b4af96127c22da62f`

This document is a concise current-state map. It does not replace canonical
schemas, accepted ADRs, implementation, tests, or detailed validation records.

## 1. Purpose

AI Instrument Assistant is a Python-centered, teaching-oriented electronics
Agent system. Its core purpose is to combine design-side EDA evidence with real
hardware measurement evidence for safe, traceable, grounded teaching and
eventual diagnosis.

The intended long-term loop is design -> test -> analysis -> diagnosis ->
design feedback. The repository has established the bounded design, hardware,
Agent-governance, and deterministic evidence foundations for that direction.
It has not completed arbitrary autonomous diagnosis or a real combined
EDA-plus-hardware workflow.

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

Only the JLCEDA API adapter may touch official `eda.*` runtime objects. The
integration exposes read-only document/selection operations and a guarded view
highlight operation. It has no arbitrary JavaScript execution, raw method
dispatch, direct VISA access, or EDA design mutation. Provider acceptance of a
highlight remains distinct from verified visual application.

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

## 4. Canonical Contracts

- [`protocols/hardware/v1/hardware-tool.schema.json`](../../protocols/hardware/v1/hardware-tool.schema.json)
  is the canonical Hardware Tool wire schema.
- [`protocols/evidence/v1/`](../../protocols/evidence/v1/README.md) is the
  canonical cross-language Evidence v1 wire contract.
- [`protocols/harness-hardware/v1/`](../../protocols/harness-hardware/v1/README.md)
  defines the independent authenticated Harness-to-Python IPC contract.
- [`protocols/jlceda/v1/`](../../protocols/jlceda/v1/README.md) defines the
  independent JLCEDA integration wire contract.

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

This proves deterministic containment for the recorded real scenarios. It does
not prove arbitrary autonomous diagnosis, unconstrained natural-language
grounding, or a combined real EDA-and-hardware loop.

## 8. Current Limitations

- Harness compatibility is proven only for the frozen reviewed commit/package
  shape above.
- The `TrustedOperationScope` invocation-budget ledger is process-local.
- Production dynamic scope issuance, persistence, and recovery are incomplete.
- `memory://` artifact references are scoped to the backend lifetime and are
  not durable storage.
- Grounding validates a constrained English claim surface; ambiguous or
  unrecognized claims fail closed.
- Hardware validation is bounded to the current DS1102Z-E workflows.
- Phase 8 has not completed a real combined EDA-plus-hardware workflow.
- Causal diagnosis is not implemented.
- Candidate next measurements remain empty/deferred.
- JLCEDA highlight submission can be accepted without programmatic proof of
  the exact visible effect.

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
- [Harness compatibility](../integrations/deepseek-harness-phase7a-compatibility.md)
- [Harness hardware adapter ADR](../adr/0004-deepseek-harness-hardware-adapter.md)
- [JLCEDA implementation constraints](jlceda-v0.2-implementation-constraints.md)
- [JLCEDA protocol state machine](aia-jlceda-v1-state-machine.md)
- [JLCEDA highlight findings](../compatibility/jlceda-phase5b4-highlight-findings.md)

## 12. Known Documentation Drift

Some point-in-time documents retain their historical status text. In
particular, the root `README.md` still describes Phase 5B.2b; the JLCEDA
extension README still describes Phase 5B.3b and says remote highlight is
disabled; and the Phase 8A.1, 8A.2, and 8B.1 documents retain pre-closeout
status headers. Use current code, canonical schemas, accepted closeouts, Git
history, tests, and `PHASE_STATUS.md` for current phase status. Do not rewrite
historical validation evidence merely to make the wording look current.

## 13. Open Context Drift Requiring Review

`ProbeSetupConfirmation.scope` carries both `requestCorrelationId` and
`workflowId`, but the current Physical Policy evaluator compares the
confirmation's request correlation and does not independently compare its
`workflowId`. The separate `TrustedOperationScope` gate does validate the
request workflow against the trusted operation scope, but that is not the same
as validating the physical confirmation's own workflow scope.

This context pack therefore preserves workflow/request scoping as a normative
invariant while explicitly recording that its independent Physical Policy
enforcement is not fully demonstrated by the current implementation/tests.
Any work touching confirmation scoping MUST stop for a Context Drift /
Architecture Proposal; this documentation task does not change production
behavior or reinterpret the prior bounded real validation runs.
