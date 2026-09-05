# JLCEDA Phase 5B.1 Real-Runtime Observation — 2026-09-05

## Record status

- Evidence type: user-executed manual smoke test in a real JLCEDA Pro editor.
- Extension under test: AI Instrument Assistant 0.2.7.
- Backend endpoint: `ws://127.0.0.1:49624` before and after restart.
- Scope: Phase 5B.1 authentication, heartbeat, transport-loss detection and
  bounded reconnect only. No EDA business operation, Agent, instrument access,
  arbitrary JavaScript execution or design mutation was enabled.
- Editor version, compiled date and client/web environment were not captured;
  this record does not infer them.

This is a record of actual editor observations reported by the user. It is not
an automated end-to-end test result.

## Direct real-editor observations

| Scenario | Observation |
| --- | --- |
| Initial connection | Authentication completed successfully. |
| Backend shutdown | The Extension detected loss of the Backend. |
| Reconnect while Backend was unavailable | The bounded retry sequence ran. |
| Backend restart | The Backend returned on the same `127.0.0.1:49624` endpoint. |
| Recovery | The Extension automatically established a new authenticated session. |
| Close handling | No `InvalidAccessError` and no illegal client-side close code `1008` were observed. |
| Async host boundary | No unhandled Promise rejection was observed. |

One host-level message may appear on the first heartbeat/liveness probe after
the Backend disappears:

```text
WebSocket is already in CLOSING or CLOSED state
```

In the observed run, this message was followed immediately by the expected
local teardown and bounded reconnect. It did not repeat as an uncontrolled send
loop, did not block recovery, and the Extension re-authenticated after the
Backend returned. It is therefore recorded as a JLCEDA runtime compatibility
observation rather than an application failure.

## Facts established by this observation

1. A real JLCEDA Extension can complete the Phase 5B.1 challenge-response flow
   against the Python loopback gateway.
2. Backend disappearance transitions the Extension into bounded recovery rather
   than leaving the old session active.
3. Restarting the Backend on the configured stable endpoint permits automatic
   re-authentication without reconfiguring the Extension.
4. The hardened client close policy avoids the previously observed illegal
   client close-code exception.
5. The hardened host callback boundary avoids the previously observed unhandled
   Promise rejection.
6. The first failed liveness send can still cause one diagnostic message inside
   the official host WebSocket implementation; successful state transition and
   recovery show that it is contained at the application boundary.

## Evidence boundary

The manual smoke test establishes actual behavior only for the runtime and
scenario described above. Automated tests separately verify state transitions,
generation isolation, timer cleanup, session invalidation and protocol
validation. Automated tests do not prove behavior inside the proprietary
JLCEDA host, while this manual observation does not replace deterministic unit
and contract coverage.

## Automatic closeout evidence

The following results were produced separately by the local automated suites
after recording the runtime observations:

- Python unit, contract and architecture tests: 79 passed.
- Shared TypeScript contract tests: 12 passed.
- TypeScript adapter, transport and architecture tests: 41 passed.
- TypeScript type checking: passed.
- Extension package build: passed for version 0.2.7.

These counts are automated evidence and are not included in the real-editor
PASS observations above.
