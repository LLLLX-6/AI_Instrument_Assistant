# AI Instrument Assistant — Phase Status

Baseline date: 2026-09-10

Current HEAD at consolidation start: `76502f9`

Status meanings:

- **COMPLETE**: reviewed and committed within its bounded claims.
- **CURRENT**: next active phase; scope is defined but implementation is not
  implied.
- **PLANNED**: direction only; exact implementation requires later review.

## Phase Ledger

| Phase | Status | Important baseline commits | Key output and bounded limitation |
| --- | --- | --- | --- |
| V0.2 Phases 1-4 | **COMPLETE** | Earlier repository history | Contract-first JLCEDA wire schemas, provider-neutral EDA domain/port, mapping, and in-memory adapter. These phases do not prove a real provider runtime. |
| Phase 5 / JLCEDA through 5B.4 | **COMPLETE** | `ebbe15a`, `7d06b1f`, `4fb4ed5`, `2656470`, `6e2bb74` | Real TypeScript extension boundary, authenticated localhost transport, read-only document/selection, and guarded highlight. Provider acceptance is not proof of exact visible highlight rendering. No EDA mutation or arbitrary JavaScript execution. |
| Phase 6 | **COMPLETE** | `a3c8619`, `af20ba0`, `f6128a7`, `834837d`, `9168712`, `ce6440c` | DS1102Z-E driver, waveform acquisition, deterministic analysis, `MeasurementService`, and five-operation `HardwareToolRuntime`; bounded real HIL evidence on firmware `00.06.03.SP2`. No general instrument family or industrial-accuracy claim. |
| Phase 7A | **COMPLETE** | `fcfab60` | Exact DeepSeek Harness compatibility baseline at commit `d347e703...` and package shape `0.1.3-alpha.1`. No future-version compatibility claim. |
| Phase 7B | **COMPLETE** | `9b42c39`, `04e3a65`, `98a85aa`, `aa87b87` | Independent authenticated Hardware IPC, persistent Python backend, Harness plugin, and bounded real hardware validation. Sent-unconfirmed requests are not replayed. |
| Phase 7C | **COMPLETE** | `3c787c3`, `168656a`, `79ec1f4`, `e81d852`, `59a05b9`, `619da9c`, `74658cd` | Governed Agent with `TrustedOperationScope`, Physical Policy, canonical evidence, Egress, Grounding, Runner boundary, and final real DeepSeek plus DS1102Z-E validation. Scope budgeting remains process-local; grounding covers a constrained English surface. The confirmation model carries workflow scope, but independent Physical Policy comparison of that field requires a Context Drift review. |
| Phase 8A.1 | **COMPLETE** | `239d004` | Reviewed unified engineering evidence architecture and evidence-category boundaries. Design only at this commit. |
| Phase 8A.2 | **COMPLETE** | `78ec167` | Evidence v1 shared contract, immutable engineering-evidence core, deterministic assembler/comparator, and evidence-only teaching projection. No diagnosis or execution authority. |
| Phase 8B.1 | **COMPLETE** | `76502f9` | Deterministic design-to-measurement workflow with cross-reference-before-comparison, source separation, explicit tolerance semantics, zero inference, and zero next-measurement generation. Uses recorded/synthetic inputs, not a live combined EDA/hardware run. |
| Phase 8B.2 | **CURRENT** | Not implemented | Real JLCEDA design context -> provider-neutral design evidence -> recorded hardware evidence -> deterministic `EngineeringEvidenceWorkflow`. This phase MUST NOT use real hardware or real DeepSeek. |
| Phase 8B.3 | **PLANNED** | None | Real JLCEDA plus real DS1102Z-E through the deterministic evidence workflow. Exact authorization and validation design is deferred. |
| Phase 8C | **PLANNED** | None | Teaching/Diagnosis Agent over `TeachingDiagnosisContext`. Causal-diagnosis semantics are not yet defined. |
| Phase 9 | **PLANNED** | None | Governed multi-step teaching/diagnosis workflow. Planning and renewed authority semantics require future review. |
| Phase 10 | **PLANNED** | None | Productization, UX, deployment, observability, and release hardening. |

## Current Next Phase: 8B.2

Goal:

```text
real JLCEDA design context
  -> provider-neutral design evidence
  -> recorded hardware evidence
  -> deterministic EngineeringEvidenceWorkflow
```

Phase 8B.2 does not authorize real hardware, real DeepSeek, causal diagnosis,
automatic next measurements, EDA mutation, or changes to Phase 7C safety
semantics.

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
- [Evidence v1 contract](../../protocols/evidence/v1/README.md)
- [Hardware Tool schema](../../protocols/hardware/v1/hardware-tool.schema.json)
- [Harness compatibility](../integrations/deepseek-harness-phase7a-compatibility.md)
- [JLCEDA protocol](../../protocols/jlceda/v1/README.md)
