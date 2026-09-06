# Phase 6G Real/Fake Hardware Tool Runtime

## Status

**Automatic implementation and contract validation: PASS. Real HardwareToolRuntime HIL: PASS with real tool-runtime evidence.**

Phase 6G establishes the first stable AI-facing hardware boundary, without connecting an Agent,
LLM, MCP runtime, JLCEDA workflow, or additional instrument type:

`HardwareToolRuntime -> MeasurementService -> OscilloscopeInterface <- real or simulated adapter`

The runtime supports exactly five semantic operations:

- `hardware.get_status`
- `hardware.measure_frequency`
- `hardware.measure_vpp`
- `hardware.capture_waveform`
- `hardware.measure_pwm`

It has no raw SCPI operation, dynamic dispatch, arbitrary driver method access, VISA resource
argument, or waveform-sample export.

## Contract and validation boundary

`protocols/hardware/v1/hardware-tool.schema.json` remains the wire-format source of truth. Phase 6G
adds explicit runtime success/error envelopes while retaining the Phase 6E request and direct DTO
definitions. Every inbound request is validated before the workflow lock and before any Service
call. Unknown operations are classified by the static allowlist as `unsupported_operation`; all
other malformed values are `invalid_request`.

The Python validator loads JSON Schema definitions at runtime. It does not reproduce argument
fields or an operation enum. Validation diagnostics expose only bounded JSON paths and schema rule
names, never submitted values or backend exception text.

Success envelopes contain `contract_version`, `ok=true`, `operation`, and `result`. Error envelopes
contain the same version and operation correlation plus a bounded error code, safe message, and
optional bounded validation issues. Successful output is JSON-safe: enums and timestamps are
converted to strings, DutyCycle carries explicit ratio/percent, and domain/driver/VISA objects do
not cross the boundary.

## Artifact and observation semantics

Waveform and PWM results expose an `ArtifactReference` plus bounded waveform metadata (channel,
point count, intervals/ranges, mode, capture time). Full `time_values` and `voltage_values` remain
inside the ArtifactStore. There is deliberately no generic artifact-dump operation.

The current store is process-local and non-durable. Repeated observations are not cached or treated
as idempotent: each call produces a new MeasurementRequest identity and capture calls produce a new
artifact identity. This is required because hardware measurements are time-varying facts.

Partial PWM results preserve Phase 6E semantics. If capture and software analysis succeed while an
instrument query fails, the response remains `ok=true`, quality is `degraded`, and available
evidence is retained. A failed result becomes a Tool error only when no meaningful result exists.

## Real and fake composition

The outer `bootstrap.hardware_tool` module is the only composition boundary that knows the backend:

- real: existing `PyVisaTransport -> DS1102ZEDriver -> deterministic analysis ->
  InMemoryArtifactStore -> MeasurementService -> HardwareToolRuntime`;
- fake: `SimulatedOscilloscope ->` the same analysis, store, Service, serializer, validator and
  HardwareToolRuntime.

Backend selection uses the explicit `HardwareBackend.REAL` or `HardwareBackend.FAKE` value. Real
requires a VISA resource at composition time. A real connection failure propagates as a real
failure and never invokes the fake builder. There is no automatic fallback.

The simulated scope produces a deterministic 10 kHz, 3.3 Vpp, 30% high-level duty waveform on CH1
and CH2. Facts read through its oscilloscope methods are explicitly labeled `source=simulated`;
software-derived observations remain `source=software_analysis`. Simulation is never presented as
physical-instrument evidence.

## Error mapping

The public taxonomy is fixed to:

| Tool code | Internal category |
|---|---|
| `invalid_request` | Schema-invalid request |
| `unsupported_operation` | Operation outside static allowlist |
| `hardware_unavailable` | Disconnected hardware |
| `instrument_connection_failed` | Connection-layer failure |
| `instrument_identity_mismatch` | Device incompatible with selected driver |
| `measurement_failed` | Semantic instrument measurement failed |
| `waveform_acquisition_failed` | No meaningful waveform/PWM result after acquisition failure |
| `analysis_failed` | Application analysis boundary failed |
| `artifact_unavailable` | Artifact storage/reference boundary failed |
| `internal_error` | Unexpected implementation failure |

Public messages are fixed and do not interpolate exception text. Raw SCPI, `VisaIOError`, stack
traces, resource names, filesystem paths, or secrets are not returned.

## Concurrency

HardwareToolRuntime serializes the complete validated Service workflow with one process-local lock.
This prevents two requests from interleaving a multi-step capture/analysis/query sequence. The
existing ScpiSession still serializes individual transport operations, providing defense in depth.
Request validation occurs before this lock because it has no hardware side effect.

This policy is process-local only. Multi-process arbitration, cancellation, queue limits, busy
responses, and distributed ownership are not implemented in this phase.

## Automatic evidence

TDD Red evidence before production implementation:

- 2 import errors for absent simulated adapter/composition modules;
- 3 architecture failures for absent runtime, fake adapter, and HIL script;
- total: 5 failing target tests.

Green coverage includes all five operations, CH1/CH2, malformed/missing/extra fields, invalid
channel, operation/kind mismatch attempts, unknown operation, pre-side-effect rejection, partial PWM,
artifact references, no sample arrays, explicit simulated source, real/fake response shape parity,
no real-to-fake fallback, typed error mapping, bounded internal failures, stable JSON serialization,
fresh request/artifact identities, whole-workflow serialization, and dependency checks.

The unified run passed 267 Python tests, 14 TypeScript shared-contract tests, and 70 TypeScript
runtime/architecture tests. Both TypeScript suites include strict no-emit typechecking. The fake
demo completed all five operations and returned Schema-valid bounded envelopes.

## HIL scripts

Fake development demo:

```powershell
.venv\Scripts\python.exe scripts\check_hardware_tool_fake.py
```

Real CH1 tool-boundary HIL candidate:

```powershell
.venv\Scripts\python.exe scripts\check_hardware_tool_runtime.py --resource "USB0::0x1AB1::0x0517::<serial>::INSTR"
```

The real script builds the concrete composition but invokes all five business operations only via
`composition.runtime.execute(...)`. It prints bounded JSON, masks the instrument serial, and never
prints waveform arrays. Before running: use only a safe low-voltage PWM source, confirm common
ground, and do not probe mains or high voltage.

## Known limitations and stop boundary

- Real HardwareToolRuntime HIL has not been run; lower layers and MeasurementService have separate
  real evidence, but that does not prove the new runtime boundary.
- Only DS1102Z-E, two logical channels, existing NORM/BYTE 1200-point capture, and the existing
  threshold-edge analysis are composed.
- Artifact storage is volatile and cannot be retrieved through a public Tool operation.
- Runtime serialization is in-process; no cross-process instrument lease exists.
- The runtime has no Agent, LLM, MCP, WebSocket, EDA coordination, DMM, signal generator, arbitrary
  SCPI, new waveform mode, or new algorithm.

## Actual real HardwareToolRuntime HIL observation

用户于 2026-09-06 使用真实 RIGOL DS1102Z-E（firmware `00.06.03.SP2`）和安全低压
CH1 PWM 完成全部五个 HardwareToolRuntime operation 的端到端验证。所有操作均返回
`ok=true`，输出由 runtime envelope 承载，并通过既定有限 DTO 边界。

| Operation / evidence | Actual result |
|---|---|
| `hardware.get_status` | DS1102Z-E；firmware `00.06.03.SP2` |
| `hardware.measure_frequency` | `10000 Hz`；source=`instrument`；quality=`good` |
| `hardware.measure_vpp` | `0.42 V`；source=`instrument`；quality=`good` |
| `hardware.capture_waveform` | ArtifactReference present；1200 points；200 ns sample interval；无完整 waveform arrays |
| `hardware.measure_pwm` instrument | frequency `10000 Hz`；Vpp `0.42 V` |
| `hardware.measure_pwm` software | frequency `10004.274084063527 Hz`；period `9.995727741935484e-05 s`；high-level duty `29.96496735825155%`；Vpp `0.416 V`；mean `-0.22408333333333333 V`；RMS `0.2695101977044035 V` |
| PWM result quality | `good`；warnings=`[]` |
| Coherence | software=`same_artifact`；instrument/software=`sequential_same_session` |

独立 capture 与 PWM capture 产生不同 Artifact ID，符合“每次调用是新观察”的非缓存语义。
Tool 输出没有 waveform sample arrays、VISA resource、raw SCPI、backend exception、Driver
object，也未连接 Agent、LLM 或 MCP。

Phase 6G 因此判定为 **PASS with real tool-runtime evidence**。结论仅覆盖当前设备、firmware
`00.06.03.SP2`、CH1、安全低压约 10 kHz/30% PWM、NORM/BYTE 和 1200-point workflow。
不声明 atomic capture、industrial-grade accuracy、persistent/cross-process Artifact、CH2 或
RAW/MAX/WORD/ASCII 已验证。
