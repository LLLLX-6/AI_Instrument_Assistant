# AIA Harness Hardware Protocol v1

This directory is the wire-format contract for `aia-harness-hardware` version
`1`. It is independent of the `aia-jlceda` protocol: the two integrations do
not share protocol names, message types, sessions, challenges, credentials,
correlation tables, or business operations.

JSON Schema is the single source of truth for individual JSON message shape.
It does **not** define message order, authentication transitions, replay rules,
session ownership, correlation, cancellation, or delivery certainty. Those
cross-message rules are defined below and enforced by the pure protocol
semantics layer before a future transport implementation is added.

## Message classes

Pre-authentication messages are `hello`, `challenge`, `prove`, `accepted`, and
`rejected`. They do not require an established session; `accepted` creates one.
Authenticated session messages are `request`, `response`, `error`, `ping`, and
`pong`, and always require `session_id`.

Every message carries `protocol`, `version`, and a unique `message_id`.
`challenge`, `prove`, `accepted`, `rejected`, `response`, `error`, and `pong`
also carry `reply_to` where defined by their schema. A receiver rejects unknown,
duplicate, late, or old-session correlations even when a message is structurally
valid.

Only these request operations exist:

- `hardware.get_status`
- `hardware.measure_frequency`
- `hardware.measure_vpp`
- `hardware.capture_waveform`
- `hardware.measure_pwm`

Arguments reference the canonical Hardware Tool Schema. There is no generic
method, command, script, resource-name, file-path, or transport passthrough.

## Authentication contract

The future server binds only to `127.0.0.1`. This protocol uses a dedicated,
random 256-bit PSK that is never shared with JLCEDA, committed, logged, or
included in tool arguments. Each connection uses a fresh client nonce, server
nonce, challenge ID, expiry, and connection generation.

The proof is base64url-without-padding HMAC-SHA256 over the UTF-8 bytes of the
following newline-separated fields, in this exact order:

```text
aia-harness-hardware
1
client_instance_id
client_nonce
server_nonce
challenge_id
expires_at
```

The backend compares the proof in constant time. A challenge is single-use and
expires at `expires_at`. Acceptance creates a fresh random session ID bound to
the connection and generation. Disconnect invalidates that session; proofs,
challenges, and messages from an old connection cannot be reused. Serialized
messages are limited to 65,536 UTF-8 bytes.

## Correlation and delivery state

Each request has one of three delivery states:

- `NOT_SENT`: no transport send was attempted.
- `SENT_UNCONFIRMED`: the request may have reached Python but no valid response
  has been correlated.
- `RESPONSE_RECEIVED`: one valid response was correlated.

Responses and adapter errors correlate through `reply_to`. The correlation key
also includes the active session and connection generation. A second response,
unknown `reply_to`, old session, or old generation is rejected. A response that
arrives after the caller stopped waiting is consumed and discarded, never
delivered to a later invocation.

No operation is automatically replayed. In particular,
`SENT_UNCONFIRMED + disconnect` produces `indeterminate_execution`, including
for `hardware.get_status` under this conservative v1 policy. A new invocation
is a new physical observation and cannot impersonate the lost result.

## Cancellation and result semantics

`CLIENT_CANCELLED_WAIT` means the Harness adapter stops waiting and discards a
later response. It does not mean `MEASUREMENT_CANCELLED`: the blocking backend
workflow may continue. Phase 7B does not claim cooperative hardware
cancellation and does not replay a cancelled invocation.

A schema-valid HardwareToolRuntime envelope, including `ok=false`, is a normal
canonical tool value. Only these boundary failures become Harness failures:
`ipc_authentication_failed`, `backend_protocol_mismatch`,
`backend_unreachable`, `backend_response_invalid`, and
`indeterminate_execution`.

No socket, server, client, or hardware implementation exists in Phase 7B.1.
