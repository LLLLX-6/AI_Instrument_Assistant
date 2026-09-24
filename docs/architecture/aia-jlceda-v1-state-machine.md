# AIA-JLCEDA Protocol v1 State Machine

JSON Schema is the single source of truth for each message's wire shape. This document is the source of truth for ordering, authentication, correlation, expiry, replay and connection lifetime rules.

## Proof bytes

Both peers compute HMAC-SHA256 over the UTF-8 bytes of these seven lines, with exactly one LF (`0x0A`) between adjacent values and no trailing LF:

1. `aia-jlceda`
2. `1.0`
3. `client_instance_id`
4. `challenge_id`
5. `client_nonce`
6. `server_nonce`
7. `expires_at` exactly as sent by the server

The result is unpadded base64url. The pre-shared secret is at least 256 random bits, is never sent on the wire, placed in a URL, or written to diagnostics. The Python verifier uses a constant-time comparison.

## Authentication transitions

| Current state | Input | Required semantic checks | Output / next state |
|---|---|---|---|
| Connected | `hello/init` | Loopback peer; no session; fresh client nonce | `hello_ack/challenge` / Challenged |
| Challenged | `hello/prove` | Same connection; matching challenge and reply IDs; unexpired; unused; valid HMAC | `hello_ack/accepted` / Authenticated |
| Challenged | invalid proof | Challenge is consumed | `hello_ack/rejected(authentication_failed)` / Connected |
| Challenged | expired proof | Challenge is consumed | `hello_ack/rejected(challenge_expired)` / Connected |
| Any | reused challenge | Challenge ID was consumed | `hello_ack/rejected(replay_detected)` |
| Authenticated | `ping` | Session belongs to this connection | Correlated `pong`; refresh last-seen |
| Any | socket disconnect | — | Remove challenges and invalidate every session for that connection |

`hello/init`, `hello_ack/challenge`, `hello/prove`, and rejected acknowledgements are pre-auth messages. `hello_ack/accepted` establishes and therefore carries the new `session_id`. Every subsequent heartbeat or business message is a session message and must carry that ID.

## Heartbeat and cancellation

The accepted acknowledgement supplies bounded heartbeat interval and timeout values. A pong must echo the ping nonce and reference its message ID. Missing heartbeats invalidate the session and cause the gateway to close the socket. Gateway shutdown cancels the monitor, closes active sockets, and invalidates their sessions.

### Extension physical transport states

The Extension owns an explicit physical lifecycle independent of the authentication states above:

```text
DISCONNECTED -> CONNECTING -> SOCKET_OPEN -> AUTHENTICATING -> AUTHENTICATED
       ^              |              |              |              |
       |              +--------------+--------------+--------------+
       |                          DISCONNECTING
       |                                |
       +---- RETRY_WAIT <---------------+
                    |
                    +---- reconnect attempt
                    +---- RECONNECT_EXHAUSTED
```

Every physical registration gets both a unique WebSocket attempt ID and a monotonically increasing connection generation. Connected callbacks, message callbacks, handshake continuations, heartbeat callbacks and reconnect timers capture that generation. They are no-ops unless it still identifies the current physical attempt. A successful authentication never reuses an old session, client nonce, server nonce or challenge.

There is no timer that pretends a socket opened. Only the official connected callback can move `CONNECTING` to `SOCKET_OPEN`. A connection timeout moves directly to retry handling without calling close on the unopened socket.

The Extension teardown order is fixed: disable sends and clear heartbeat/connect timers, optionally perform a best-effort close, then in a `finally` path invalidate session and correlation state, release the physical attempt and schedule at most one reconnect timer. Disconnect is idempotent while disconnecting, disconnected, waiting to retry, exhausted, or stopped.

The Extension calls `SYS_WebSocket.close` only for a locally initiated shutdown of the current generation after that generation reached `SOCKET_OPEN`. It does not call close after a connection failure, a send failure that proves the socket dead, backend disappearance, or a stale-generation callback. This avoids asking the official host to close a socket that is still connecting or already closed.

Client-initiated WebSocket close codes are an application mapping and are not protocol messages:

| Code | Meaning |
|---|---|
| `1000` | Normal Extension stop |
| `4001` | Authentication failure |
| `4002` | Heartbeat timeout |
| `4003` | Protocol violation |
| `4004` | Session or correlation invalid |
| `4005` | Local transport failure |

Codes `4002` and `4005` remain reserved application mappings; current dead-socket and timeout paths deliberately do not call close. The official runtime boundary rejects every other client close code before calling `SYS_WebSocket.close`.

Reconnect uses one bounded sequence of 500 ms, 1 s, 2 s, and 5 s against the same configured loopback endpoint. Each retry uses a new physical attempt ID. Successful authentication cancels retry state, creates a fresh session, and starts a fresh heartbeat. Exhaustion is explicit and requires the user to configure the backend connection again. The production gateway CLI defaults to stable port `49624` and rejects port `0`; an explicitly configured port must match the Extension endpoint.

Official host callbacks are synchronous boundaries: they always return `undefined`. Synchronous callback failures and rejected callback Promises are consumed and routed to finite transport diagnostics so no rejection can escape into the JLCEDA host event loop.

## Authenticated business request lifecycle

The authenticated read allowlist includes `eda.document.get_active`,
`eda.selection.get`, and the additive `eda.design.get`. The Python
gateway sends it only after exactly one authenticated session is active. The
request `message_id` is its request identity; a response must carry the same
session, operation and trace identifiers and name that request in
`reply_to_message_id`.

The gateway owns one pending future per request message ID. A response completes
that future at most once. Unknown, duplicate, wrong-session, wrong-operation or
wrong-trace responses are protocol violations and never reach a mapper. Timeout
removes the pending entry. Socket disconnect fails every pending request for that
physical connection. A later authenticated connection has a new session and
cannot complete requests from the previous connection generation.

JSON Schema enforces individual request/response shape, the static operation
name, required session/correlation fields and bounded payload/error fields. The
rules in the previous paragraph are cross-message semantics and are enforced by
the transport lifecycle, not claimed as Schema guarantees.

Unknown operations, malformed JSON, binary frames, and unknown fields are
rejected before business dispatch. Guarded `eda.view.highlight` remains a
separate, explicitly authorized presentation operation; it is not part of the
read-only observation path.

For `eda.selection.get`, the Extension reads current document identity, then
the finite selection DTO, then current document identity again. A missing first
document produces `no_active_document`; a missing or different second document
produces `inconsistent_observation`. Only after both identities agree does the
Extension generate one new AIA `snapshot_id` shared by the document reference,
selected object references, and safely derived net references. This is a
coherent observation window, not an atomic provider snapshot, native revision,
content version, or stale-proof.

For `eda.design.get`, the same document-before/document-after coherence rule
wraps one bounded full-design read. Truncation or a changed document fails
closed. Its generated snapshot identifies only that observation; it is not a
provider revision, freshness proof, or design immutability guarantee.

Selected wire, component, and unsupported primitive types remain distinct.
Provider primitive IDs and finite native type names are retained, but official
objects and runtime summaries never cross the protocol boundary. A derived net
is created only from a non-empty network name actually observed on a wire; it
has no invented native ID, endpoints, source, or signal expectation. A bounded
selection that was truncated is rejected instead of silently represented as a
complete Domain selection.
