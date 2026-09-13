# Phase 8.5B — Real JLCEDA Design Smoke Attempt 2

Status: **NOT PASS — STATUS SNAPSHOT CLIENT COMPLETION BLOCKER**

Date: 2026-09-13

This record covers the single newly authorized bounded real JLCEDA smoke for
the reviewed Phase 8.5B runtime-coordination repair. The earlier real smoke
record remains unchanged and historical. No automatic retry or production
patch was performed during this attempt.

## Production boundary exercised

- The production Python composition started separate loopback listeners on
  `49624` for AIA-JLCEDA v1 and `49626` for aia-interactive/v1. Hardware was
  inactive.
- The production design-selection issuer was composed; no fake authority or
  test-only server was installed.
- Both listener ports had one real connection. The interactive Host audit
  recorded one authenticated JLCEDA frontend connection.
- The user observed a fresh `Connected` indication. The server recorded one
  initial authoritative snapshot, so the repaired initial
  `SYNCHRONIZING -> workflow_snapshot -> CONNECTED` path completed.

The JLCEDA editor version was not freshly captured by this attempt. The
separate historical compatibility record contains the previously observed
runtime version and is not promoted to a new observation here. The production
extension artifact used for this validation was the reviewed v0.2.16 build.

## Primary regression result

The first explicit production Status action failed and displayed the bounded
Host-unavailable message. Stop-time server counters prove that the interactive
server received exactly one explicit snapshot request and sent exactly one
snapshot reply. No interactive command was received or dispatched.

Therefore the old server-reader starvation boundary was crossed successfully:
the request reached Python, the Host snapshot path completed, and the reply
was sent. The Status action did not render successfully. Available bounded
diagnostics cannot distinguish among delivery to the TypeScript callback,
frame/session acceptance, waiter correlation, or the final Dialog boundary.
No narrower cause is invented.

Under the approved fail-fast procedure this is **NOT PASS**. The run stopped
immediately. Selection, trusted design selection, replay, ProbeTarget, reload,
post-reload Status, cross-menu, and cancellation checks were not attempted.

## Bounded observed counts

| Observation | Count/result |
| --- | ---: |
| Extension activation | at least 1; exact callback count not exposed |
| Interactive authenticated connections | 1 |
| Interactive reconnects | 0 observed |
| Initial authoritative snapshots sent | 1 |
| Explicit Status snapshot requests received | 1 |
| Explicit Status snapshot replies sent | 1 |
| Explicit Status snapshot successes | 0 |
| Interactive commands received | 0 |
| Interactive command dispatches | 0 |
| Interactive command failures | 0 |
| Selection events | 0 exercised after the stop condition |
| Host-side fresh observations | 0 |
| Design-selection Challenges | 0 |
| Valid design-selection answers | 0 |
| Trusted design-selection decisions | 0 |
| Rejected replays | 0 |
| ProbeTargets | 0 |
| Cancellations | 0 |
| Operation Challenge answers | 0 |
| Physical Challenge answers | 0 |
| EDA design writes | 0 |
| Hardware executions | 0 |
| VISA sessions | 0 |
| SCPI operations | 0 |
| DeepSeek requests | 0 |

The provider authentication result and exact JLCEDA-side snapshot-receive
count were not independently exposed by the bounded validation runner and are
not reconstructed from TCP state.

## Security and protocol result

The record contains no credential, HMAC proof, raw frame, raw provider
payload, sensitive design identifier, host path, VISA resource, instrument
serial, waveform, stack, or model output. No EDA mutation, physical authority,
operation authority, Hardware action, measurement, or model call occurred.
Evidence v1, AIA-JLCEDA v1, aia-interactive/v1, Hardware canonical,
Harness-Hardware v1, teaching-claims/v1, and publication contracts were not
changed.

## Conclusion

Initial authoritative synchronization passed, and the explicit Status request
now reached the production Python snapshot construction and reply-send
boundary. End-to-end Status completion still failed. Phase 8.5B therefore
remains **REAL JLCEDA DESIGN UI NOT PASS**. This attempt is consumed; another
real retry requires a separate review and fresh explicit authorization.
