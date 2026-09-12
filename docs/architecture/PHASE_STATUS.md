# AI Instrument Assistant — Phase Status

Baseline date: 2026-09-12

Committed implementation baseline before Phase 8C.2B: `c5866e2`

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
| Phase 9 | **PLANNED / NOT STARTED** | None | Guided Engineering Reasoning & Diagnosis roadmap only: proposal-only next measurement, reviewed inference rules, structured hypotheses, causal-diagnosis policy, then human-authorized iteration. |
| Phase 10 | **PLANNED** | None | Productization, UX, deployment, observability, and release hardening. |

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

## Next Major Phase: 9 — Planned / Not Started

Phase 9 is the Guided Engineering Reasoning & Diagnosis roadmap only. No Phase
9 implementation, execution authority, or real external action is authorized.

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
- [Evidence v1 contract](../../protocols/evidence/v1/README.md)
- [Hardware Tool schema](../../protocols/hardware/v1/hardware-tool.schema.json)
- [Harness compatibility](../integrations/deepseek-harness-phase7a-compatibility.md)
- [JLCEDA protocol](../../protocols/jlceda/v1/README.md)
