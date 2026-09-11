# Phase 8B.3 Real Validation Attempt 2

Status: **PASS — accepted by Phase 8B.3 closeout architecture review**

Evidence source: bounded completed-run output supplied by the user. This record
does not reconstruct omitted real identifiers, measurement values, provider
payloads, secrets, or local configuration.

## Bounded observations

- Real JLCEDA design projection returned `PROJECTED` for target `PWM_OUT`.
- Trusted design selection, a new bounded operation authorization, and a new
  physical confirmation completed for this run.
- `hardware.get_status` reported channel `null`, Scope `ALLOW`, Physical Policy
  `ALLOW`, delivery `RESPONSE_RECEIVED`, IPC dispatch count 1, and semantic
  Hardware execution count 1.
- `hardware.measure_pwm` reported channel 1, Scope `ALLOW`, Physical Policy
  `ALLOW / allowed_confirmed_physical_setup`, delivery `RESPONSE_RECEIVED`, IPC
  dispatch count 1, and semantic Hardware execution count 1.
- The receipt therefore preserved the validated semantic invocation channel:
  status has no channel and PWM is CH1. No post-receipt normalization was used.
- Evidence admission succeeded and the cross-reference state was
  `VERIFIED_LINK`.
- Every reported comparison was `INDETERMINATE` with reason
  `TOLERANCE_UNSPECIFIED`.
- Engineering inference count, teaching inference count, candidate-next-
  measurement count, and model-request count were all zero.
- Snapshot semantics remained `observation_identity_only`; no provider revision
  or document-immutability claim was made.

The two semantic Hardware executions comprise one status observation and one
physical PWM measurement. No automatic retry or remeasurement is represented.

The supplied bounded summary did not expose numeric instrument/software values,
quality details, warnings, raw IDs, or artifact metadata. They are deliberately
not reconstructed here. The established Evidence v1 path preserves instrument
facts and software analyses separately and keeps artifact references opaque.

Attempt 1 remains a separate historical NOT PASS record. Attempt 2 used a new
run/workflow/request, design decision, operation scopes, physical confirmation,
measurement context, and evidence context; their concrete values are omitted.
No further real execution is authorized by this record.
