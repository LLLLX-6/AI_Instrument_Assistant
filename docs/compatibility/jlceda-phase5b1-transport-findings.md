# JLCEDA Phase 5B.1 Transport Compatibility Findings

Reviewed and closed on 2026-09-05 after automated verification and a
user-executed smoke test in a real JLCEDA Pro editor.

## Frozen transport baseline

- Extension: AI Instrument Assistant 0.2.7.
- Backend endpoint: stable loopback `ws://127.0.0.1:49624`.
- Transport: official `eda.sys_WebSocket` boundary through
  `JlcEdaApiAdapter`.
- Authentication: pre-shared-key HMAC-SHA256 challenge-response.
- Reconnect delays: 500 ms, 1 s, 2 s and 5 s.
- Enabled protocol operations: handshake and heartbeat only.

## Actual JLCEDA runtime observations

The following statements come from the real-editor manual smoke test, not from
fakes or CI:

1. Initial authentication succeeded.
2. Backend shutdown was detected.
3. Bounded reconnect ran while the Backend was unavailable.
4. Restart on the same endpoint led to automatic re-authentication.
5. No illegal-`1008` `InvalidAccessError` was observed.
6. No unhandled Promise rejection was observed.
7. One host diagnostic, `WebSocket is already in CLOSING or CLOSED state`, may
   appear on the first heartbeat/liveness probe after Backend disappearance.
   The application immediately entered bounded reconnect and recovered. This
   is classified as a contained host-runtime compatibility observation, not an
   application failure.

The detailed evidence record is
[`jlceda-phase5b1-real-runtime-observation-2026-09-05.md`](../manual-tests/jlceda-phase5b1-real-runtime-observation-2026-09-05.md).

## Automatic verification findings

The automated suites are deterministic evidence for code owned by this
project. They verify:

- schema agreement across Python and TypeScript;
- HMAC, nonce, challenge, session and replay rules;
- immediate server-side session invalidation on socket loss;
- explicit physical connection states and generation isolation;
- no heartbeat send from stale generations;
- no close call for an unopened or already-proven-dead socket;
- at most one local close per physical attempt;
- idempotent teardown and a single reconnect scheduler;
- new physical WebSocket ID and new session after reconnect;
- synchronous, rejection-consuming callbacks at the official host boundary;
- static API allowlisting and the absence of dynamic code execution.

These tests simulate transport edges and inspect application behavior. They do
not claim to execute inside or verify the proprietary JLCEDA WebSocket host.

Closeout results: 79 Python tests, 12 shared TypeScript contract tests and 41
TypeScript adapter/transport/architecture tests passed. Type checking and the
0.2.7 Extension package build also passed.

## Compatibility decision

Phase 5B.1 transport is accepted for its intended authentication-and-heartbeat
scope. The isolated first failed-send diagnostic is tolerated because it is the
liveness observation that triggers controlled recovery and has no continuing
side effect in the validated runtime.

This acceptance does not authorize Phase 5B.2 business operations, broaden the
static semantic operation allowlist, or relax any read-only and no-arbitrary-
JavaScript safety boundary.
