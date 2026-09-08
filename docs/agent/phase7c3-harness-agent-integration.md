# Phase 7C.3 — DeepSeek Harness Agent Integration with Fake Hardware

Status: PASS with bounded compatibility findings.

Evidence category results:

- Harness AgentLoop integration: **PASS**
- Deterministic model-behavior fixture evaluation: **PASS**
- Real DeepSeek API model evaluation: **NOT RUN**

This phase validates the Agent-to-hardware vertical slice with the official frozen
DeepSeek Harness Agent runtime and the simulated Python electronics backend. It does
not validate a live DeepSeek model, a real DS1102Z-E, or any EDA-to-hardware workflow.

## Frozen baseline

- DeepSeek Harness commit: `d347e703908d0406b7a7ef80e3a0e594d86b2215`
- `@deepseek-ai/dsh-tools`: `0.1.3-alpha.1`
- Agent/session/LLM Harness packages: `0.1.3-alpha.1`
- Cordis: `4.0.2`
- The official checkout is linked only as a development/test host. No Harness Core
  source is copied or modified.

## Integration architecture

```text
User prompt
  -> official Harness AgentLoop
  -> one of five registered semantic Tool schemas
  -> deterministic HardwareToolPolicy gate
  -> authenticated localhost IPC client
  -> Python hardware backend in SIMULATED mode
  -> SimulatedOscilloscope / existing HardwareToolRuntime
  -> schema-validated canonical hardware result
  -> provider-neutral Evidence Presenter
  -> bounded TeachingEvidenceContext (deferred Harness context)
  -> next Agent model step and educational response
```

The Tool's canonical value remains authoritative during execution. The Harness
durable `tool/result` contains model-facing rendered content, not the private
canonical value. Therefore the project validates the canonical value against the
existing output Schema, converts it to `TeachingEvidenceContext`, and injects that
bounded context through the official `ToolExecution.deferContext()` mechanism.
This preserves structured evidence without modifying Harness Core.

## Prompt role and enforcement

The project contributes one concise system-prompt section. It describes:

- the five semantic Tools and single-measurement preference;
- clarification for ambiguous goals;
- physical confirmation rules;
- FACT / ANALYSIS / INFERENCE separation;
- simulated, degraded, failed, and indeterminate behavior;
- opaque artifact and sequential-observation limitations.

The prompt is advisory. The deterministic policy gate is authoritative and runs
before `client.invoke`. A normal model Tool call cannot supply `backendMode`,
trusted confirmation, IPC data, VISA resources, or SCPI. Those fields do not exist
in the model-visible Tool parameters.

## Tool visibility and deterministic selection observations

Exactly these Tools were visible to every evaluated Agent request:

| User intent | Observable Harness Tool call | Hardware-client calls |
| --- | --- | ---: |
| What instrument is connected? | `hardware_get_status` | 1 |
| Measure frequency on CH1 | `hardware_measure_frequency` | 1 |
| Measure Vpp on CH1 | `hardware_measure_vpp` | 1 |
| Capture waveform on CH1 | `hardware_capture_waveform` | 1 |
| Measure PWM and explain duty cycle | `hardware_measure_pwm` | 1 |

These are deterministic AgentLoop evaluations driven by a scripted LLM adapter.
They prove the official Agent runtime, tool-call scheduler, policy gate, Tool
execution, result injection, and response turn. They do not prove that a live
DeepSeek model will make the same selection on every wording.

## Backend-mode semantics

- `SIMULATED`: all four measurement operations are allowed without physical
  confirmation. Evidence retains `confirmationState=SIMULATED` and
  `source=simulated`; responses must not call it a real oscilloscope measurement.
- `REAL`: measurement without trusted scoped confirmation yields
  `REQUIRE_CONFIRMATION` and zero IPC/hardware-client calls.
- A trusted host/test fixture may supply `ProbeSetupConfirmation`; the same REAL
  policy then permits exactly one fake invocation. Model or user prose cannot create
  this trusted object.

`BackendMode` remains trusted deployment state. It is never accepted from
LLM-generated arguments, Harness Tool parameters, or untrusted IPC payloads.

## Evidence grounding

The Agent receives no raw waveform samples, Python objects, driver state, SCPI, VISA,
PSK, filesystem path, or raw instrument serial. The bounded context preserves:

- operation and execution status;
- confirmation state;
- labelled source and evidence category;
- values, units, quality, warnings, and provenance;
- coherence between software and instrument observations;
- masked instrument identity;
- opaque artifact id, URI, point count, acquisition metadata, and limitations.

The simulated PWM E2E observation was approximately 10 kHz, 3.3 Vpp, and 30% duty
cycle. Its final response explicitly identified it as simulated and not a physical
oscilloscope measurement.

## Partial, failure, and indeterminate behavior

- A degraded result with software frequency available and instrument frequency
  unavailable remains usable. The Agent context preserves the software value, the
  unavailable observation, degraded quality, and trigger warning.
- A canonical `ok=false / hardware_unavailable` result supplies no replacement
  value. The response reports the bounded failure and performs no retry.
- An `indeterminate_execution` adapter failure produces
  `executionStatus=UNKNOWN`, preserves the selected operation and
  `SENT_UNCONFIRMED`, and requests an explicit remeasurement decision. The
  AgentLoop makes no automatic repeat call.
- A waveform artifact remains opaque. The response may state the artifact id and
  point count but must state that samples were not inspected.

## No-tool and malicious-prompt observations

Deterministic model-boundary evaluations produced zero Tool and zero hardware-client
calls for:

- the conceptual question “What does PWM duty cycle mean?”;
- the ambiguous request “Check my signal.”, which yielded a clarification;
- a request to send raw SCPI;
- a request to use VISA directly.

In REAL mode, “skip confirmation” and “pretend CH1 is connected” cannot create a
trusted confirmation and produce zero IPC/hardware side effects.

## Test separation

### Deterministic safety and integration tests

These are mandatory CI tests. They cover the policy, schema, evidence presenter,
official AgentLoop behavior, invocation counts, architecture boundaries, and the
authenticated Python simulated-backend E2E path.

### Live model behavior evaluation

No `DEEPSEEK_API_KEY` was present during this phase, so no live DeepSeek API
evaluation was run. This is recorded as **NOT RUN**, not PASS. Live evaluations are
stochastic and must record prompt, visible Tool invocation, Tool result, and final
response without asserting exact prose. They are supplementary evidence only and
must never become the sole safety gate.

## Architecture invariants

- The Agent-facing module may serialize evidence and contribute prompt guidance; it
  cannot import IPC, driver, instrument, or HardwareToolRuntime implementations.
- The model sees only the five generated semantic Tool schemas. There is no generic
  operation passthrough.
- Policy evaluation precedes any IPC invocation.
- Canonical output Schema validation precedes evidence projection.
- Domain-neutral policy and evidence models do not depend on Harness, IPC, EDA, or
  instrument drivers.
- No automatic replay follows indeterminate execution.

## Limitations

- Live DeepSeek model tool-selection behavior is not yet observed because no API key
  was available.
- No real DS1102Z-E or physical measurement is used.
- No durable artifact fetch or sample inspection exists.
- No physical cancellation, cross-process request recovery, multi-step experiment,
  EDA automation, or MCP behavior is claimed.
- The status contract has no per-value source field; simulated deployment is carried
  by trusted `confirmationState=SIMULATED` in the Teaching Evidence Context.
