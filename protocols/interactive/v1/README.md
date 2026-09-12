# AIA Interactive Protocol v1

`aia-interactive/v1` is the additive, unprivileged frontend protocol for the
AI Instrument Assistant Application Host. JSON Schema in this directory is the
single source of truth for wire shape. It does not define authentication,
ordering, freshness, replay, challenge consumption, or session ownership.

## Authority boundary

The protocol may carry connection negotiation, typed application commands,
safe snapshots/status, Host-issued challenges, untrusted challenge answers,
events, cancellation, and cursors. It never carries a preconstructed trusted
design decision, `TrustedOperationScope`, `ProbeSetupConfirmation`, arbitrary
Tool/EDA method/SCPI, raw provider payload, waveform array, model prompt, or
secret.

An authenticated frontend is allowed to submit supported messages. It is not
authorized to perform an operation. Only the Host may resolve and atomically
consume an exact challenge and then invoke an existing trusted issuer.

## Protocol state machine

```text
DISCONNECTED
  -> hello
NEGOTIATING
  -> hello_ack(accepted) -> SESSION_ACTIVE
  -> hello_ack(rejected) -> DISCONNECTED
SESSION_ACTIVE
  -> command | challenge_answer | event subscription
  -> disconnect -> DISCONNECTED
```

Session messages require the accepted `application_generation` and `session_id`.
Reconnect creates a new connection generation/session. A current authoritative
snapshot is delivered before events after a valid cursor. Cursors are delivery
positions only and grant no trust.

Challenge validation order is: authenticated connection, Schema validation,
Host workflow/challenge resolution, frontend kind, application generation,
workflow revision, expiry, nonce, exact binding, atomic consumption, trusted
issuer call, transition commit. Any failure produces zero authority, IPC,
hardware action, and budget consumption.

## Bounds

Messages are limited to 65,536 UTF-8 bytes by the gateway. Identifiers, text,
arrays, operations, status, snapshots, and event payloads have explicit Schema
bounds. Unknown fields fail closed.

## Frozen protocol separation

This contract does not modify Evidence v1, AIA-JLCEDA v1, Hardware canonical,
Harness-Hardware v1, teaching-claims/v1, or harness-publication-bridge/v1.
