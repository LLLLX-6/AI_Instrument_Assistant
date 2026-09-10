# Physical Confirmation Workflow Binding

Status: **PASS — remediation completed and architecture reviewed.**

Baseline before remediation:
`eff9a4192096cfca1f5dc6b45204d9b47bfda6dd`.

## Root Cause

`ProbeSetupConfirmation.scope.workflowId` already represented the workflow that
received a physical setup confirmation, while Physical Policy validated only
the confirmation request correlation. `TrustedOperationScope` separately
validated its own workflow, but that did not prove that the physical
confirmation belonged to the current workflow. The missing independent
comparison allowed the two authorization meanings to drift.

## Decision

Physical confirmation and semantic operation authorization retain independent
workflow bindings. `HardwareToolPolicyContext` now carries one immutable
`workflowId`. At the Harness composition boundary this identity comes from the
trusted host `TrustedOperationScopeContext`, never from model text, Tool
arguments, IPC payloads, or `TeachingEvidenceContext`.

The composition boundary rejects a Policy Context whose workflow differs from
the trusted host workflow. This is a consistency check; it does not merge the
Operation Scope and Physical Policy models.

For REAL physical measurements, Physical Policy independently compares:

```text
HardwareToolPolicyContext.workflowId
==
ProbeSetupConfirmation.scope.workflowId
```

A mismatch returns:

- decision: `REQUIRE_CONFIRMATION`;
- reason: `physical_confirmation_workflow_mismatch`;
- delivery state at the Tool boundary: `NOT_SENT`;
- IPC dispatches: zero;
- hardware side effects: zero.

The workflow check is additive. Trusted source, request correlation, channel,
target, low-voltage confirmation, common-ground confirmation when required,
and unchanged wiring retain their existing behavior. SIMULATED measurement
behavior remains unchanged and does not acquire a physical-confirmation
workflow requirement.

## Independent Gates

The execution order remains:

```text
Schema validation
  -> TrustedOperationScope preflight
  -> Physical Policy
  -> final scope authorization / budget consumption
  -> IPC
```

Operation Scope workflow matching cannot compensate for a physical
confirmation issued to another workflow. Conversely, a matching physical
confirmation cannot compensate for an Operation Scope workflow mismatch. The
latter still stops before Physical Policy, preserving zero policy evaluation,
zero IPC, and zero hardware effect.

## Scope and Compatibility

This repair changes only provider-neutral policy context, deterministic policy
evaluation, Harness composition, tests/support call sites, and current-state
documentation. It does not change `TrustedOperationScope`, canonical Hardware
Schema, `HardwareToolRuntime`, `MeasurementService`, drivers, SCPI/VISA,
Grounding, Egress, Evidence v1, `EngineeringEvidenceWorkflow`, or JLCEDA.

Historical Phase 7C reports remain unchanged. They are bounded observations of
the implementation used at the time and are not rewritten by this prospective
repair.

Compatibility result: **PASS**. Trusted workflow identity was available from
Host/Application state at the existing composition boundary. The repair did
not require merging Operation Scope with Physical Policy, changing
`HardwareToolRuntime`, or altering Tool execution ordering.
