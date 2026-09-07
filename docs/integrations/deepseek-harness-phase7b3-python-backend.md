# Phase 7B.3: Python Harness-Hardware IPC Backend

Status: **PASS** — Phase 7B.3 architecture review approved the automated
fake-backend implementation. No DeepSeek Harness plugin, Agent, LLM, MCP,
JLCEDA change, artifact fetch, or real hardware HIL is included.

This PASS establishes the Python authenticated IPC backend boundary only. It
does not claim that a DeepSeek Harness plugin has been validated, that a real
DS1102Z-E has been exercised through this IPC path, that physical measurement
can be cancelled, that artifacts are durably persisted, or that requests can be
recovered across Python backend process restarts.

## Server architecture

```text
future TypeScript Harness client
  -> ws://127.0.0.1:49625
  -> aia-harness-hardware/v1 schema validation
  -> authentication/session/correlation state
  -> HardwareRuntimePort.execute(canonical request)
  -> HardwareToolRuntime
```

The server core sees only `HardwareRuntimePort.execute()` and a canonical
response validator. It neither imports nor calls Rigol, PyVISA, SCPI, waveform
analysis, MeasurementService, JLCEDA, or Agent code. The composition root is the
only layer that selects the existing fake or real HardwareToolRuntime graph.

## Lifecycle and configuration

`HarnessHardwareServer.start()` loads an exactly 32-byte secret and binds only
`127.0.0.1`. Port `49625` is the explicit default; port `0` is reserved for
tests/development. No measurement happens during server initialization.

`stop()` stops new connections, closes sessions, stops heartbeat tasks, waits
for already dispatched runtime work to settle, releases the socket, and removes
the secret from server state. It does not attempt to interrupt an instrument
operation midway.

The CLI accepts `--backend fake|real`, fixed loopback host, port, and real
backend configuration. It never accepts a PSK value on the command line. There
is no real-to-fake fallback: a real composition error remains explicit.

## Secret handling and authentication

The default credential location is
`.aia-secrets/harness-hardware-psk.txt`. Loading never creates a missing key.
Only explicit `--initialize-secret` bootstrap generates 32 random bytes, writes
base64url without padding using exclusive creation, and requests user-only file
permissions where the platform supports them. Neither the key nor its path is
included in protocol messages, runtime calls, audit records, or success logs.

Each connection moves through:

```text
CONNECTED_PREAUTH -> CHALLENGE_ISSUED -> AUTHENTICATED
                  -> CLOSING -> CLOSED
```

The server issues a fresh server nonce, challenge ID, expiry, connection
generation, and session ID. HMAC-SHA256 uses the exact field order frozen in the
v1 protocol README. Comparison is constant-time. Wrong, expired, reused,
out-of-order, and malformed proofs fail before any runtime action.

## Session and generation isolation

Every authenticated message must match the session bound to its current socket.
A copied session from another connection and every previous session are
rejected. Connection generations increase for the lifetime of one server
instance. Runtime completions check the original context, session, and
generation immediately before sending, so an old callback cannot mutate or
deliver into a replacement connection.

## Validation and static dispatch

Inbound text is limited to 65,536 UTF-8 bytes. WebSocket `max_size` rejects
oversized frames before application JSON handling where possible; the server
also verifies encoded size before JSON interpretation. Binary, malformed JSON,
and invalid envelopes cause bounded rejection or close policy.

Every parsed message is validated against `aia-harness-hardware/v1` before
cross-message state checks. Request arguments reference the canonical Hardware
Tool Schema. The server then permits only the five frozen operations and builds:

```json
{
  "contract_version": "1.0",
  "operation": "one fixed allowlisted operation",
  "arguments": {}
}
```

It invokes the runtime's single semantic `execute()` port. There is no method
name lookup, script evaluation, command forwarding, raw hardware operation, or
dynamic import.

## Results and errors

A canonical HardwareToolRuntime value—including `ok=false`—is validated and
returned inside a normal protocol `response`. It is not converted to an IPC
failure. An invalid runtime value becomes the bounded
`backend_response_invalid` adapter error without returning exception details.

Server-side protocol codes are separate from hardware error codes:

- `protocol_invalid`
- `authentication_failed`
- `session_invalid`
- `message_too_large`
- `duplicate_message`
- `operation_not_allowed`
- `backend_response_invalid`
- `adapter_internal_error`

Pre-authentication failures use the frozen `rejected` codes. User-facing frames
never contain stack traces, PSK/HMAC values, SCPI, VISA resources, secret paths,
or waveform sample arrays.

## Correlation and duplicate policy

Every response/error `reply_to` is copied from the validated request's
`message_id`. The server retains a bounded process-level ledger (default 4,096
completed IDs) in addition to per-connection in-flight state. Any duplicate ID,
whether in-flight, completed, or replayed by a new session while retained, is
rejected with `duplicate_message`. Results are never cached as general
measurement responses and duplicate delivery never re-invokes the runtime.

The bounded ledger means very old completed IDs may eventually be evicted. UUID
uniqueness and the client's no-replay contract remain mandatory; durable
cross-process exactly-once execution is not claimed.

## Disconnect, retry, and cancellation

After request dispatch, disconnect does not cancel the blocking Python
workflow. The runtime may complete, but the generation guard discards its result
and records only bounded correlation metadata. It is never moved to another
session and never replayed. The future client therefore retains the frozen
`SENT_UNCONFIRMED + disconnect -> indeterminate_execution` classification.

No cancellation message or hardware cancellation capability is added. A
future Harness abort can only mean `CLIENT_CANCELLED_WAIT`; it cannot claim
`MEASUREMENT_CANCELLED`.

## Concurrency and heartbeat

The adapter accepts a bounded maximum of eight dispatched runtime tasks. It
adds no second workflow lock: calls run through the existing
HardwareToolRuntime, whose lock remains the authoritative serialization
boundary. This avoids weakening or replacing the proven concurrency behavior.

Session-bound ping/pong tracks transport liveness using bounded interval and
timeout values. Heartbeat does not invoke HardwareToolRuntime, query the
instrument, consume error queues, or create artifacts.

## Fake composition and smoke client

Automated end-to-end tests use the real fake graph:

```text
SimulatedOscilloscope
  -> MeasurementService
  -> HardwareToolRuntime
  -> HarnessHardwareServer
  -> HarnessHardwareDevClient
```

The standalone development smoke command is:

```powershell
.venv\Scripts\python.exe scripts\check_harness_hardware_ipc.py
```

It creates an ephemeral in-memory secret, starts only the fake backend, performs
the full handshake, invokes all five operations, prints bounded result summaries,
and shuts down. It is not the future TypeScript Harness plugin.

To run the persistent development backend after explicitly initializing its
secret:

```powershell
.venv\Scripts\python.exe -m ai_instrument_assistant.integrations.harness_hardware.cli --backend fake --initialize-secret
```

## Known limitations

- No TypeScript Harness client or plugin exists yet.
- Cancellation cannot stop an already running hardware workflow.
- Request-ledger retention is bounded and in-memory, not durable across process
  restarts.
- `memory://` waveform references remain opaque and valid only during the
  Python backend/artifact-store lifetime.
- Real DS1102Z-E HIL is intentionally deferred.
