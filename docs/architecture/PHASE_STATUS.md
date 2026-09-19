# AI Instrument Assistant — Phase Status

Baseline date: 2026-09-12

Committed implementation baseline before Phase 8.5A: `4a7be88`

Status meanings:

- **COMPLETE**: reviewed and committed within its bounded claims.
- **CURRENT**: next active phase; scope is defined but implementation is not
  implied.
- **UNDER REVIEW**: implementation and automated validation exist, but the
  phase is not complete until architecture review and closeout.
- **ARCHITECTURE REVIEW**: a design proposal exists, but implementation has not
  started and no execution authority is implied.
- **PLANNED**: direction only; exact implementation requires later review.

## Phase Ledger

| Phase | Status | Important baseline commits | Key output and bounded limitation |
| --- | --- | --- | --- |
| V0.2 Phases 1-4 | **COMPLETE** | Earlier repository history | Contract-first JLCEDA wire schemas, provider-neutral EDA domain/port, mapping, and in-memory adapter. These phases do not prove a real provider runtime. |
| Phase 5 / JLCEDA through 5B.4 | **COMPLETE** | `ebbe15a`, `7d06b1f`, `4fb4ed5`, `2656470`, `6e2bb74` | Real TypeScript extension boundary, authenticated localhost transport, read-only document/selection, and guarded highlight. Provider acceptance is not proof of exact visible highlight rendering. No EDA mutation or arbitrary JavaScript execution. |
| Phase 6 | **COMPLETE** | `a3c8619`, `af20ba0`, `f6128a7`, `834837d`, `9168712`, `ce6440c` | DS1102Z-E driver, waveform acquisition, deterministic analysis, `MeasurementService`, and five-operation `HardwareToolRuntime`; bounded real HIL evidence on firmware `00.06.03.SP2`. No general instrument family or industrial-accuracy claim. |
| Phase 7A | **COMPLETE** | `fcfab60` | Exact DeepSeek Harness compatibility baseline at commit `d347e703...` and package shape `0.1.3-alpha.1`. No future-version compatibility claim. |
| Phase 7B | **COMPLETE** | `9b42c39`, `04e3a65`, `98a85aa`, `aa87b87` | Independent authenticated Hardware IPC, persistent Python backend, Harness plugin, and bounded real hardware validation. Sent-unconfirmed requests are not replayed. |
| Phase 7C | **COMPLETE** | `3c787c3`, `168656a`, `79ec1f4`, `e81d852`, `59a05b9`, `619da9c`, `74658cd` | Governed Agent with `TrustedOperationScope`, Physical Policy, canonical evidence, Egress, Grounding, Runner boundary, and final real DeepSeek plus DS1102Z-E validation. Scope budgeting remains process-local; grounding covers a constrained English surface. Historical validation records remain unchanged. |
| Phase 8A.1 | **COMPLETE** | `239d004` | Reviewed unified engineering evidence architecture and evidence-category boundaries. Design only at this commit. |
| Phase 8A.2 | **COMPLETE** | `78ec167` | Evidence v1 shared contract, immutable engineering-evidence core, deterministic assembler/comparator, and evidence-only teaching projection. No diagnosis or execution authority. |
| Phase 8B.1 | **COMPLETE** | `76502f9` | Deterministic design-to-measurement workflow with cross-reference-before-comparison, source separation, explicit tolerance semantics, zero inference, and zero next-measurement generation. Uses recorded/synthetic inputs, not a live combined EDA/hardware run. |
| Phase 8B.2 | **COMPLETE** | `2eff54a` | Real read-only JLCEDA design evidence plus an exact trusted Host/user selection decision was combined with recorded Hardware evidence through the deterministic `EngineeringEvidenceWorkflow`. No real hardware, model, EDA write, diagnosis, or inference was used. |
| Phase 8B.3 | **COMPLETE** | `4252376` | Attempt 1 remains historical NOT PASS (`hardware / receipt_semantics_invalid`). After the approved receipt-channel repair, separately authorized real Attempt 2 returned PASS with correct status-null/PWM-CH1 provenance, verified linkage, tolerance-unspecified comparisons, and zero inference/model calls. The private contract and authorization are validation-only. |
| Phase 8C.1 | **COMPLETE** | `f26050d` | Provider-neutral deterministic claim-slot policy over `TeachingDiagnosisContext`; exact evidence/comparison/limitation claims only. Content hashes grant no trust, and ALLOW is not sufficient for publication. No model, execution, knowledge corpus, inference, hypothesis, causal diagnosis, or next-measurement authority. |
| Phase 8C.2A | **COMPLETE** | `c5866e2` | Minimal structured candidate protocol, Host-owned projection and aliases, strict parser, deterministic engineering Grounding, canonical English renderer, fail-whole fallback, final-Egress port, and bounded audit are reviewed and complete without any model or external execution. |
| Phase 8C.2B | **COMPLETE** | `e53fc98` | One-attempt provider-neutral orchestration, private bounded process bridge, frozen zero-Tool `LlmRuntime.stream()` route, strict stream/Egress/parser/Grounding/renderer boundaries, deterministic fallback, and independent final Egress. One authorized real request passed safety Case B; no Schema-valid real-model candidate was observed. |
| Phase 8 | **COMPLETE** | This closeout commit | Trusted real design and Hardware evidence can feed deterministic engineering evidence and bounded teaching publication while an untrusted model has no authority over facts, comparison semantics, inference, diagnosis, or execution. |
| Phase 8.5 | **LIMITED INTEGRATION** | Phase 8.5A closeout commit | Phase 8.5A is complete. Phase 8.5B is CLOSED FOR NOW / LIMITED INTEGRATION; Phase 8.5C remains planned and has not started. |
| Phase 8.5A | **COMPLETE** | This closeout commit | Authoritative Python Host, finite workflow/CAS, one-time Challenges, additive `aia-interactive/v1`, reconnect/status/cancellation, fake frontends, lifecycle/bootstrap seams, and offline tests. No permanent UI or real external runtime. |
| Phase 8.5B | **CLOSED FOR NOW / LIMITED INTEGRATION** | Uncommitted implementation follows `d5ce8f8` | Attempts 1–4 remain historical NOT PASS. Real diagnostics proved the canonical object API works in a stable Provider context, while ID reconstruction is lossy (2 selected IDs resolved to 1 primitive). Version 0.2.26 retains safe bounded stabilization, but reliable automatic current UI-selection capture remains host-state-sensitive. Automatic candidate binding, trusted selection, and `ProbeTarget` derivation that depend on it are deferred. No further real run is authorized. |
| Phase 8.5C | **PLANNED / NOT STARTED** | None | Harness-owned operation authorization, physical confirmation, hardware workflow, and teaching interaction surface. |
| Phase 8.5D | **PLANNED / NOT STARTED** | None | Separately authorized real interactive E2E only after 8.5A-C closeout. |
| RE-001A | **FUNCTIONALLY COMPLETE / EDA PROVIDER LIMITED** | Uncommitted bounded implementation | Provider-neutral RC design/theory path and deterministic topology service are complete. Yuanlitu negative real validation passed; the positive provider runtime attempt stopped at health, so positive provider compatibility is not claimed. |
| RE-001B | **COMPLETE — MEASUREMENT CORE** | Uncommitted bounded implementation | User-declared or observed roles feed a deterministic single-point plan and analyzer. No automatic source control, sweep, cutoff search, or generalized experiment framework. |
| RE-001C-Lite | **COMPLETE — REAL GOVERNED DATA-FLOW PROVEN** | Uncommitted bounded implementation | Four one-shot Scope/Physical Policy/IPC/real DS1102Z-E operations produced canonical results, four typed measurements, and deterministic analysis without retry. |
| RE-001D-Lite | **COMPLETE — REAL CONVERSATIONAL E2E PROVEN** | Uncommitted bounded implementation | A natural-language request reached trusted physical confirmation, governed real measurement, strict mapping, deterministic analysis, one-shot DeepSeek selection, grounded fallback, and safe final publication. This is data-flow proof, not RC-filter performance validation. |
| RE-001 Core Milestone | **CORE E2E PROOF COMPLETE** | Closeout pending coherent commits | The current core conversational experiment chain is proven within its bounded scopes. Full EDA/simulation integration, sweep, automatic source control, report export, and generalized diagnosis remain deferred. |
| Phase 9 | **PLANNED / NOT STARTED** | None | Guided Engineering Reasoning & Diagnosis roadmap only: proposal-only next measurement, reviewed inference rules, structured hypotheses, causal-diagnosis policy, then human-authorized iteration. |
| Phase 10 | **PLANNED** | None | **Release & Deployment Hardening**: installer, signing, updater, durable operational state, production observability, OS sandboxing, packaging/distribution, and release engineering. Core interactive UX belongs to Phase 8.5. |

## Completed Context Drift Remediation

Physical Confirmation Workflow Binding is implemented and regression validated
and its architecture review is complete. Physical Policy independently compares
trusted current workflow identity with
`ProbeSetupConfirmation.scope.workflowId`; mismatch requires confirmation and
produces zero IPC. This is a narrow safety consistency repair, not a new major
phase and not a rewrite of Phase 7C history.

See
[Physical Confirmation Workflow Binding](physical-confirmation-workflow-binding.md).

## Completed Phase: 8B.3

Goal:

```text
real JLCEDA design evidence
  + real DS1102Z-E evidence
  -> deterministic EngineeringEvidenceWorkflow
```

Phase 8B.3 architecture, automated implementation, Attempt 1 diagnostic repair,
and closeout are approved. Attempt 1 remains historical NOT PASS; separately
authorized Attempt 2 returned bounded PASS. No further real run is authorized.
The JLCEDA snapshot remains observation identity only; trusted design selection
is distinct from provider primary selection and physical confirmation;
`VERIFIED_LINK` does not prove design immutability. Without explicit tolerance,
comparisons remain `INDETERMINATE / TOLERANCE_UNSPECIFIED`. No causal diagnosis
occurred, and validation-only authority is not durable production authority.

## Completed Phase: 8C.1

The provider-neutral deterministic sufficiency evaluator and immutable
claim-policy envelope are implemented, automatically validated, and
architecture reviewed. Only exact evidence restatements, supported
deterministic comparison statements, and limitation statements can be allowed.
Content hashes are identity only; ALLOW remains insufficient for publication;
and comparison interpretation binds exact status plus reason. All
knowledge-dependent teaching, engineering inference, hypothesis, causal
diagnosis, and next-measurement proposals remain explicitly blocked.

## Completed Phase: 8C.2A

The deterministic Phase 8C.2A structured candidate and guarded publication
boundary is implemented, regression validated, and architecture reviewed. Its
candidate contains no factual prose, numeric values, or Tool/action fields;
Host-owned bindings are validated as claims rather than authority; and factual
publication is produced only by deterministic rendering followed by final
Egress.

## Completed Phase: 8C.2B

Phase 8C.2B implementation, offline validation, architecture review, and one
separately authorized real-model safety validation are complete. The real run
was approved PASS Case B: the stream completed and passed raw Egress, the
Schema-invalid candidate was discarded, and deterministic fallback passed
canonical rendering and final Egress. A valid-candidate happy path was not
observed. Tool, IPC, EDA, Hardware, remeasurement, retry, and repair counts
were zero. The one-time model authorization is consumed.

## Completed Major Phase: 8

Phase 8 established provider-neutral evidence, deterministic design-to-
measurement orchestration, bounded real EDA/Hardware integration, deterministic
claim policy, and guarded teaching publication with an untrusted model. It did
not implement next-measurement proposals, engineering inference, hypotheses,
causal diagnosis, or autonomous experimentation.

## Completed Intermediate Phase: 8.5A

Phase 8.5 provides interactive adapters and runtime orchestration so normal
users can operate the completed Phase 8 capabilities from Harness and JLCEDA
without validation scripts or CLI confirmation tokens. The proposal keeps one
authoritative Python Application Host and preserves all existing selection,
Scope, Physical Policy, evidence, Grounding, and Egress boundaries.

The Phase 8.5A offline foundation is approved and complete. It adds no
permanent frontend UI and performed no real JLCEDA, Hardware, VISA, or model
action. See
[Phase 8.5 Interactive Productization](phase8_5-interactive-productization.md)
and
[Phase 8.5A Application Host & Runtime Lifecycle](phase8_5a-application-host-runtime.md).

## Phase 8.5B — Closed for Now / Limited Integration

Phase 8.5B.0 is reviewed PASS and freezes UI-B `OFFICIAL_DIALOG_FALLBACK` plus
Transport-C `SEPARATE_INTERACTIVE_LISTENER_REQUIRED`. Phase 8.5B.1 now wires
the real production composition from the interactive listener through the Host
and provider-neutral EDA application path to the separate AIA-JLCEDA v1
gateway. Async provider I/O is lock-free and guarded against stale return.
Hardware, VISA, measurement, DeepSeek, arbitrary JavaScript, raw EDA dispatch,
and EDA design mutation remain prohibited. The production authority repair
composes the existing Python trusted design-selection factory only;
Harness-owned operation Scope and physical confirmation remain deferred to
Phase 8.5C. The first real smoke proved both authenticated connections and two
Host-side observations but remains historical NOT PASS. The offline runtime-
coordination repair is approved. Separately authorized Attempt 2 proved the
explicit Status request reached Python and a reply was sent, but client-side
completion still failed, so it is also NOT PASS. Both authorizations are
consumed. The offline client-completion repair passed review, but separately
authorized Attempt 3 stopped at Gate A because the explicit Status action did
not dispatch a snapshot request to the server. Attempts 1, 2, and 3 are
consumed; any later real JLCEDA read/UI smoke requires a separate review and
fresh explicit approval.

Phase 8.5B is now **CLOSED FOR NOW / LIMITED INTEGRATION**. The retained
surface includes extension activation, Provider and Interactive connections,
ApplicationHost integration, the private cross-VM MessageBus command bridge,
Status, manual Refresh, read-only EDA integration, and the existing security,
authority, and bounded stabilization controls. Reliable automatic current
JLCEDA UI-selection capture remains host-state-sensitive in the reviewed 3.x
runtime and is explicitly deferred. Consequently, typed candidate binding
originating from that capture, trusted design selection depending on it, and
automatic `ProbeTarget` derivation are also deferred. This disposition does
not alter Attempts 1–4 or any later compatibility evidence.

## Next Major Phase: 9 — Planned / Not Started

Phase 9 is the Guided Engineering Reasoning & Diagnosis roadmap only. No Phase
9 implementation, execution authority, or real external action is authorized.

## Completed RE-001 Core E2E Proof

RE-001A/B/C-Lite/D-Lite now establish the bounded path from provider-neutral
design context or an explicit user-declared fallback, through deterministic
planning and governed real measurement, to strict mapping, deterministic
analysis, provenance-separated evidence, one-shot model claim selection, and
safe grounded publication. The final real validation is recorded in
[RE-001D-Lite Final Real Conversational E2E](../validation/re001d-lite-final-real-conversational-e2e.md).

The bounded REAL Rigol interactive Web path (real DS1102Z-E via the
Harness Web: trusted confirmation, four one-shot scopes, four ordered
instrument measurements, preserved instrument provenance, grounded
publication) is recorded in
[RE-001D Real Rigol Interactive Web E2E](../validation/re001d-real-rigol-web-e2e.md).

This completion does not start a new development phase. Reliable native
JLCEDA selection, Yuanlitu positive-provider runtime validation, SimulIDE,
automatic signal generation and sweep, cutoff search, full RC physical
validation, report export, and generalized diagnosis remain deferred.

## Status Authority and References

This ledger records current status. Point-in-time ADR and validation status
headings remain historical context and may describe what had not yet been
approved at that time.

- [Project baseline](PROJECT_BASELINE.md)
- [Architecture invariants](ARCHITECTURE_INVARIANTS.md)
- [Phase 7C closeout](../agent/phase7c-closeout.md)
- [Phase 7C.4F final real validation](../agent/phase7c4f-final-real-grounded-validation.md)
- [Phase 8A.1 architecture](phase8a1-unified-engineering-evidence.md)
- [Phase 8A.2 architecture](phase8a2-engineering-evidence-core.md)
- [Phase 8B.1 workflow](phase8b1-evidence-workflow.md)
- [Phase 8B.2 workflow](phase8b2-real-jlceda-recorded-hardware-workflow.md)
- [Phase 8B.2A trusted selection disambiguation](phase8b2a-trusted-design-selection-disambiguation.md)
- [Phase 8B.3 real EDA and real hardware workflow](phase8b3-real-eda-real-hardware-workflow.md)
- [Phase 8B.3 real validation attempt 1](../validation/phase8b3-real-validation-attempt-1.md)
- [Phase 8B.3 real validation attempt 2](../validation/phase8b3-real-validation-attempt-2.md)
- [Phase 8C.1 claim policy](phase8c1-inference-sufficiency-teaching-policy.md)
- [Phase 8C.2 structured model publication proposal](phase8c2-structured-model-publication.md)
- [Phase 8C.2B DeepSeek structured candidate integration](phase8c2b-deepseek-structured-candidate-integration.md)
- [Phase 8C.2B bounded real validation](../validation/phase8c2b-real-deepseek-validation.md)
- [Phase 8 closeout](phase8-evidence-grounded-teaching-closeout.md)
- [Phase 8.5 Interactive Productization](phase8_5-interactive-productization.md)
- [Phase 8.5A Application Host & Runtime Lifecycle](phase8_5a-application-host-runtime.md)
- [Phase 8.5B JLCEDA interaction surface](phase8_5b-jlceda-interaction-surface.md)
- [Phase 8.5B.1 runtime composition remediation](phase8_5b1-runtime-composition-remediation.md)
- [Phase 8.5B runtime coordination repair](phase8_5b2-interactive-runtime-coordination-repair.md)
- [Phase 8.5B real JLCEDA smoke Attempt 2](../validation/phase8_5b-real-jlceda-design-smoke-attempt-2.md)
- [Phase 8.5B client completion repair](phase8_5b3-client-completion-boundary-repair.md)
- [Phase 8.5B real JLCEDA smoke Attempt 3](../validation/phase8_5b-real-jlceda-design-smoke-attempt-3.md)
- [Phase 8.5B menu runtime bridge](phase8_5b4-jlceda-menu-runtime-bridge.md)
- [Phase 8.5B real JLCEDA smoke Attempt 4](../validation/phase8_5b-real-jlceda-design-smoke-attempt-4.md)
- [Phase 8.5B selection stabilization repair](phase8_5b5-selection-stabilization-repair.md)
- [Phase 8.5B.0 compatibility spike](../validation/phase8_5b0-jlceda-ui-compatibility-spike.md)
- [Evidence v1 contract](../../protocols/evidence/v1/README.md)
- [Hardware Tool schema](../../protocols/hardware/v1/hardware-tool.schema.json)
- [Harness compatibility](../integrations/deepseek-harness-phase7a-compatibility.md)
- [JLCEDA protocol](../../protocols/jlceda/v1/README.md)
