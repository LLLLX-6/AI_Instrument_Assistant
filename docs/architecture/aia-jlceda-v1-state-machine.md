# AIA-JLCEDA Protocol v1 State Machine

Status: Phase 1 boundary definition. Transition implementation begins in Phase 3.

JSON Schema is the single source of truth for the wire-format structure of an
individual message. It does not define message ordering, correlation, nonce use,
session ownership, replay protection, or legal protocol transitions. Those rules
belong to this protocol state machine and its executable semantic tests.

## Message classes

### Pre-authentication messages

- `hello/init`
- `hello_ack/challenge`
- `hello/prove`
- `hello_ack/accepted`
- `hello_ack/rejected`

The first three messages do not require a `session_id`. An accepted acknowledgement
creates the session. A rejected acknowledgement terminates the handshake attempt.

### Session messages

- `ping`
- `pong`
- `eda.document.get_active` request and response
- `eda.selection.get` request and response
- `eda.view.highlight` request and response

Every session message requires a valid `session_id` issued by a completed handshake.

## State outline

```text
DISCONNECTED
  -> WAITING_FOR_INIT
  -> WAITING_FOR_PROOF
  -> AUTHENTICATED
  -> CLOSED
```

Only `hello/init` is legal in `WAITING_FOR_INIT`. Only a matching `hello/prove` is
legal in `WAITING_FOR_PROOF`. Business and heartbeat messages are legal only in
`AUTHENTICATED`.

The Phase 3 state-machine specification and tests will define at least:

- handshake and nonce correlation;
- handshake expiry and replay rejection;
- session creation and ownership;
- ping/pong correlation;
- business response correlation;
- invalid-transition handling;
- session close and re-authentication behavior.

