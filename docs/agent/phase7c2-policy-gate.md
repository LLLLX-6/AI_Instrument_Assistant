# Phase 7C.2: Deterministic Hardware Policy Gate and Evidence Presentation

Status: **IMPLEMENTED FOR REVIEW — automated fake/simulated scope**
(2026-09-08).

This phase implements the deterministic boundary between a Harness Hardware
Tool request and IPC, plus a deterministic conversion from canonical Hardware
results into bounded teaching evidence. It does not implement an LLM planner,
natural-language teaching generation, real-hardware policy HIL, automatic EDA
execution, artifact retrieval, new operations, or new analysis.

## 1. Execution boundary

```text
Harness registered Tool request
  -> canonical projected argument validation
  -> trusted HardwareToolPolicyContext provider
  -> evaluateHardwareToolPolicy
       ALLOW                -> client.invoke -> authenticated IPC
       REQUIRE_CONFIRMATION -> bounded NOT_SENT failure
       DENY                 -> bounded NOT_SENT failure
```

The policy evaluation occurs in the registered Tool's `execute` function before
`client.invoke`. Both non-allow decisions therefore create zero IPC requests,
zero Python calls, and zero hardware effects. Argument validation also occurs
before policy evaluation, so free-form or additional Tool arguments cannot carry
a forged confirmation.

Prompt-level guidance is advisory for model behavior. Deterministic policy
enforcement is authoritative for real tool execution.

## 2. PolicyContext

`HardwareToolPolicyContext` is an immutable, provider-neutral value assembled by
a trusted application boundary. It contains:

- canonical requested operation and channel;
- explicit `REAL` or `SIMULATED` backend mode;
- request correlation and bounded user goal;
- requested physical target reference, when known;
- whether common-ground confirmation is required;
- an explicit wiring-changed signal;
- optional trusted `ProbeSetupConfirmation`;
- optional prior indeterminate execution state; and
- optional provider-neutral design document/snapshot/probe-target references.

It contains no Harness object, LLM message, SCPI, VISA resource, Driver, raw EDA
object, secret, or transport object. Factories normalize and validate inputs and
freeze nested values. There is no time-based authorization expiry: elapsed time
does not prove either that wiring changed or that it remained unchanged.

## 3. Physical setup confirmation

`ProbeSetupConfirmation` is not a boolean. It records:

- confirmation ID and `TRUSTED_USER_EVENT` source;
- who confirmed;
- exact oscilloscope channel;
- physical target reference when known;
- separate safe-low-voltage and common-ground decisions;
- timezone-bearing capture text supplied by the trusted host; and
- request/workflow scope.

A CH1 confirmation cannot authorize CH2. A target mismatch, request-scope
mismatch, or explicit wiring change requires reconfirmation. EDA context is only
a candidate design reference and never creates a physical confirmation. The Tool
input Schema has no confirmation fields, so model prose cannot construct this
trusted value.

The real plugin's default context provider intentionally has no physical
confirmation. Consequently, real measurement calls fail closed until a future
reviewed UI/application event store supplies a trusted context provider.

## 4. Static risk mapping

Risk is a fixed allowlist, never inferred from operation spelling:

| Canonical operation | Risk |
| --- | --- |
| `hardware.get_status` | `SAFE_OBSERVATION` |
| `hardware.measure_frequency` | `PHYSICAL_MEASUREMENT` |
| `hardware.measure_vpp` | `PHYSICAL_MEASUREMENT` |
| `hardware.capture_waveform` | `PHYSICAL_MEASUREMENT` |
| `hardware.measure_pwm` | `PHYSICAL_MEASUREMENT` |

Unknown operations return `DENY / operation_not_policy_allowed`.

## 5. Policy decisions and reason codes

Each immutable `PolicyDecision` contains `decision`, stable `reasonCode`, a
bounded explanation, and required confirmation fields.

Decisions are `ALLOW`, `REQUIRE_CONFIRMATION`, and `DENY`. Current reason codes:

- `allowed_safe_observation`
- `allowed_simulated_measurement`
- `allowed_confirmed_physical_setup`
- `physical_setup_confirmation_required`
- `channel_confirmation_mismatch`
- `unsafe_voltage_not_confirmed`
- `grounding_not_confirmed`
- `physical_target_confirmation_mismatch`
- `confirmation_scope_mismatch`
- `wiring_change_requires_reconfirmation`
- `indeterminate_previous_execution`
- `untrusted_confirmation_source`
- `operation_not_policy_allowed`

Required fields are similarly bounded: channel, safe low voltage, common ground,
physical target, and explicit remeasurement decision.

## 6. Real and simulated behavior

`hardware.get_status` is allowed without probe confirmation in both modes. In
`REAL` mode, all four measurement operations require complete, matching,
trusted confirmation. In explicitly configured `SIMULATED` mode, measurement is
allowed without physical confirmation; canonical observation source remains
`simulated` and the presenter labels it as such.

The default mode is `REAL`. There is no runtime fallback from real to simulated.
The Fake E2E test opts into `SIMULATED` explicitly. Backend mode is currently a
trusted deployment setting rather than a backend-attested protocol field; this
is recorded as a limitation and must be reviewed before real Agent HIL.

Architecture invariant: `BackendMode` is trusted deployment state. It MUST NOT
be accepted from LLM-generated arguments, Harness Tool parameters, or untrusted
IPC payloads.

## 7. Indeterminate retry policy

When the same operation/channel/target has a prior
`INDETERMINATE_EXECUTION`, the gate returns `REQUIRE_CONFIRMATION /
indeterminate_previous_execution` unless trusted state records an explicit user
decision to measure again. Reconnect does not change this decision and does not
replay the request. Cancellation after send also cannot be treated as proof of
physical cancellation.

## 8. EDA handoff

The policy carries only bounded design references:

```text
DesignDocument / SelectionContext / ProbeTarget reference
  -> candidate target
  -> explicit user event
  -> scoped ProbeSetupConfirmation
  -> policy evaluation
```

Design snapshot identity and physical confirmation remain separate evidence.
No JLCEDA concrete type is imported, no EDA operation is called, and no automatic
EDA-to-hardware flow is implemented.

## 9. Evidence taxonomy

`EvidenceKind` is closed to `FACT`, `ANALYSIS`, and `INFERENCE`.

- canonical `instrument` observations become `FACT`;
- canonical `software_analysis` observations become `ANALYSIS`;
- canonical `simulated` observations remain explicitly sourced as simulated and
  are accompanied by a non-physical limitation;
- the deterministic presenter creates no `INFERENCE` items.

Engineering conclusions remain the responsibility of a later teaching layer
and must stay within the context's explicit inference boundary.

## 10. Evidence presenter

`presentHardwareResult` converts an already canonical Hardware result into an
immutable `TeachingEvidenceContext`. Each `EvidenceItem` preserves:

- kind and semantic label;
- numeric, duty-cycle, string, or unavailable value;
- unit;
- canonical source and quality;
- warnings;
- observation method/time;
- analysis algorithm summary where applicable; and
- evidence artifact identifiers.

The context separately preserves masked instrument identity, result quality,
coherence, warnings, failure, and bounded limitations. The presenter does not
average values, decide design compliance, or generate natural-language Agent
answers.

## 11. Partial and failure behavior

For `ok=true / quality=degraded`, all available FACT and ANALYSIS evidence is
kept. Unavailable observations retain null values and their warnings. The
context is `COMPLETED`, not falsely changed to failure.

For canonical `ok=false`, the context is `FAILED`, carries only bounded
operation/error information, and has empty facts, analyses, and inferences.
Nothing from a previous result is substituted.

For adapter `indeterminate_execution`, `presentAdapterFailure` returns
`executionStatus=UNKNOWN` and
`requiredUserAction=EXPLICIT_REMEASURE_DECISION`. It does not assert that the
measurement happened or failed.

## 12. Artifact handling

Waveform evidence retains the opaque artifact reference and bounded acquisition
metadata: ID, URI, media type, optional size/hash, channel, point count, sample
interval, ranges, acquisition mode, and capture time. It is marked `opaque=true`.

The presenter never fetches the URI and has no sample-array field. A
`memory://` URI remains backend-lifetime scoped and cannot support claims of
durable storage, plotting, sample inspection, or new analysis.

## 13. TeachingEvidenceContext

The future teaching layer receives:

- requested goal and measurement-decision reason;
- operation and execution status;
- confirmation state and required user action;
- facts, analyses, and an initially empty inference section;
- masked instrument summary;
- quality, warnings, coherence, and opaque artifact metadata;
- bounded failure/limitations; and
- a statement of the permitted inference boundary.

For the validated PWM-shaped fixture, this structure keeps instrument frequency
and Vpp as FACT, software frequency/duty/Vpp as ANALYSIS, identifies shared
waveform evidence and sequential non-atomic acquisition, and produces no
hard-coded conclusion about a 10 kHz / 30% target.

## 14. Architecture boundaries

- `src/policy` imports no Harness, IPC, Driver, Rigol, VISA, JLCEDA adapter, or
  LLM dependency.
- `src/evidence` imports no Harness runtime, Driver, VISA, or LLM dependency.
- the Harness adapter depends inward on provider-neutral policy and calls it
  before IPC;
- HardwareToolRuntime, MeasurementService, protocol schemas, Driver, SCPI, and
  JLCEDA integration are unchanged;
- prompt text is tested as documentation, while source-order and zero-call tests
  verify deterministic enforcement.

## 15. Automated evidence

The Phase 7C.2 suite uses only fake/simulated paths. Tests cover the static risk
map, all four real confirmation gates, complete confirmation, channel/target/
wiring/scope invalidation, EDA candidate isolation, default deny, prior
indeterminate execution, object immutability, zero invocation on confirmation or
denial, exactly one invocation on allow, FACT/ANALYSIS mapping, no automatic
inference, partial results, warnings/coherence/provenance, opaque artifacts,
canonical failure, indeterminate adapter status, simulated source, and defensive
serial masking.

The frozen Harness Fake E2E explicitly declares simulated mode and exercises all
five existing operations. No DS1102Z-E is connected by these tests.

## 16. Known limitations and next review gate

1. A real trusted user-confirmation event store/UI is not implemented. The real
   default therefore safely blocks measurement operations.
2. Backend mode is explicit trusted configuration, not yet authenticated backend
   metadata. It never falls back automatically and defaults to real.
3. Confirmation invalidation is driven by channel, target, scope, and explicit
   wiring-change state. There is deliberately no arbitrary clock expiry.
4. `TeachingEvidenceContext` is exported for a future teaching layer but no LLM
   consumes it in this phase.
5. No real-hardware policy HIL, autonomous planning, automatic retry,
   artifact access, durable evidence, or automatic EDA handoff is claimed.

Phase 7C.2 must be reviewed before adding a trusted confirmation UI/store or any
real Agent + DS1102Z-E validation.
