# Phase 7B.5: Real Harness Hardware HIL

Status: **PASS with bounded runtime observations** (2026-09-08).

This validation covers the frozen DeepSeek Harness adapter, authenticated
localhost IPC, the persistent Python electronics backend, HardwareToolRuntime,
and a real Rigol DS1102Z-E. It does not validate an LLM/Agent workflow, durable
artifact persistence, physical cancellation, or cross-process request recovery.

## Preconditions

The user explicitly confirmed a safe low-voltage source, approximately 10 kHz
and 30% PWM, common signal/scope ground, CH1 on the intended node, a stable CH1
display, and a stable local instrument frequency measurement before HIL began.

## Automatic regression evidence

The following results come from repeatable automated checks, not from the real
JLCEDA runtime or from an LLM/Agent session.

- Python: 332 tests passed.
- JLCEDA TypeScript contract/runtime/architecture: 84 tests passed.
- Harness TypeScript unit/contract/architecture: 33 tests passed.
- Harness frozen ToolRuntime + Python fake backend E2E: 1 test passed.
- Strict Harness TypeScript typecheck passed.
- Unified Python/TypeScript entry passed.
- Production build passed (`extensions/deepseek-harness/dist/index.js`).
- `git diff --check` passed.
- Canonical Hardware JSON Schema, HardwareToolRuntime, MeasurementService,
  Rigol Driver, and SCPI behavior have no Phase 7B.5 diff.

## Actual real-hardware observations

The following results are bounded observations from the user-confirmed physical
DS1102Z-E setup. They are distinct from the automated regression evidence above.

The final full run used the frozen Harness commit
`d347e703908d0406b7a7ef80e3a0e594d86b2215` and dsh-tools
`0.1.3-alpha.1`.

| Operation | Canonical observation |
| --- | --- |
| `hardware.get_status` | `ok=true`; Rigol DS1102Z-E; firmware `00.06.03.SP2`; serial `***9517` |
| `hardware.measure_frequency` | `ok=true`; quality `good`; instrument frequency `10040.16 Hz` |
| `hardware.measure_vpp` | `ok=true`; quality `good`; instrument Vpp `0.396 V` |
| `hardware.capture_waveform` | `ok=true`; 1200 points; sample interval `2e-7 s`; voltage range `[-0.372, 0.028] V`; opaque `memory://` artifact reference |
| `hardware.measure_pwm` | `ok=true`; quality `good`; instrument `10040.16 Hz`, `0.396 Vpp`; software `10004.334688185148 Hz`, `29.964552612083274%` duty, `0.4 Vpp` |

Every canonical result containing instrument identity used the same masked
serial. Rendered text did not expose a serial number. No accuracy threshold was
invented; instrument and software values are recorded as sequential evidence.

An invalid channel was rejected locally with the exact bounded message
`Hardware tool arguments are invalid.` The adapter classified it as
`invalid_tool_arguments` with delivery state `NOT_SENT`; the IPC client was not
invoked, so neither the Python backend nor hardware could receive that request.

## Reconnect observation

The final lifecycle-only run observed:

- generation 1 authenticated;
- backend disappearance transitioned through disconnected/retry states;
- reconnect attempts followed approximately 0.5 s, 1 s, and 2 s delays;
- generation 4 re-authenticated on the same `127.0.0.1:49625` endpoint;
- the authenticated session changed;
- connection generation advanced;
- no old request replay was observed;
- recovered `hardware.get_status` returned a canonical masked identity;
- all five tools remained registered.

The recovery completed before the scripted offline probe ran. The validation
script therefore records `backend_recovered_before_offline_probe` as a legal
race outcome rather than misclassifying successful recovery as a failure. A
separate earlier observation while the backend remained absent returned the
bounded message `Hardware backend is unavailable.`

## Compatibility findings

1. A relative secret path is resolved from the Extension process working
   directory. The real smoke test must use one shared absolute secret path (or a
   deliberately aligned working directory) for both processes.
2. Interactive stop/restart prompts can race with bounded reconnect. The smoke
   runner now accepts either a confirmed offline failure or a recovery that
   completes before the offline probe, while still requiring a new session and
   a later connection generation.
3. The frozen checkout's pnpm store contained `@standard-schema/spec@1.1.0`
   but lacked its top-level junction. Restoring that environment-only junction
   allowed strict typecheck without changing frozen source or the project lock.
4. Waveform references use the current in-memory artifact store and are not
   durable across backend restarts.

## Security inspection

The model-visible canonical/rendered results contained no full instrument
serial, VISA resource, SCPI command, secret/HMAC material, local filesystem
path, stack trace, or waveform sample arrays. The temporary PSK and build output
remain ignored and are not intended for Git.
