# Phase 8B.3 Real Validation Attempt 1

Status: **NOT PASS — historical evidence**

This record is immutable historical evidence. It does not authorize a retry.

## Bounded observations

- Real JLCEDA observation and trusted design disambiguation succeeded.
- The separate operation-authorization and physical-confirmation actions
  succeeded.
- `hardware.get_status` reached Scope ALLOW and Physical Policy ALLOW, returned
  `RESPONSE_RECEIVED`, and recorded one IPC dispatch and one semantic Hardware
  execution.
- `hardware.measure_pwm` reached Scope ALLOW and Physical Policy ALLOW, returned
  `RESPONSE_RECEIVED`, and recorded one IPC dispatch and one semantic Hardware
  execution.
- The bounded receipt reported status channel `null`, as required, but also
  reported PWM channel `null` even though the trusted PWM invocation was CH1.
- Python rejected the completed receipt as
  `hardware / receipt_semantics_invalid` before evidence assembly.
- No `TeachingEvidenceContext`, verified cross-reference, engineering context,
  diagnosis context, or model request was produced.

The two semantic Hardware executions comprise one status observation and one
physical PWM measurement. They must not be described as two physical
measurements.

The historical workflow, request, scopes, and physical confirmation are spent
and cannot be reused. Any future real validation requires fresh trusted
identities, explicit operation authorization, and physical confirmation.
