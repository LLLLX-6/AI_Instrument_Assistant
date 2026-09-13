# Phase 8.5B — Interactive Runtime Coordination Repair

Status: **OFFLINE REPAIR APPROVED; REAL ATTEMPT 2 NOT PASS**

Date: 2026-09-13

The first real Phase 8.5B smoke remains historical **NOT PASS**. This repair
used only offline tests and ephemeral loopback test sockets; it did not connect
to JLCEDA, EDA, Hardware, VISA, SCPI, or DeepSeek.

Architecture review approved this repair. A separately authorized real Attempt
2 then proved initial synchronization plus Python receipt and reply-send for
one explicit Status request, but the JLCEDA Status action did not complete.
That attempt remains **NOT PASS** and is recorded separately without changing
the approved offline implementation.

## Diagnosed defects

The interactive server had one inbound consumer, but that consumer awaited an
entire asynchronous `design.observe` dispatch inline. While the provider call
was pending, the same consumer could not read a later `snapshot_request`.
The client bounded an explicit status refresh at three seconds while the EDA
boundary may remain pending for up to five seconds, so the local request could
time out without reaching the Host snapshot lookup during that interval.

The extension had two separate reload/selection defects. A debounced selection
that completed while the client was authenticating or synchronizing was
silently dropped instead of being represented as current-state refresh work.
Also, an asynchronous presentation-only selection read did not recheck its
listener generation after `await`, so a disposed generation could complete its
callback late. The historical smoke did not capture sufficient bounded
counters to reconstruct which of these boundaries was last reached by its
final selection event; this document does not invent that missing fact.

## Repair

The server still has exactly one inbound WebSocket consumer. It now schedules
at most one validated application command separately, allowing authentication
control traffic and authoritative snapshot requests to be serviced while EDA
I/O is pending. Wire/session validation occurs before scheduling. Application
or provider failure is contained to a bounded command-failure category, and a
current authoritative snapshot is returned without exposing a stack or raw
payload. A send lock serializes the heartbeat, event, command, and snapshot
writers. Disconnect cancels the one command task and both existing pump tasks.

Bounded server counters now distinguish initial snapshots, explicit snapshot
requests/replies, received commands, dispatches, and command failures. They
contain no message bodies, credentials, identifiers, paths, or exception text.

The TypeScript client now has an explicit `SYNCHRONIZING` state. The server's
existing initial snapshot immediately follows `hello_ack`; the client accepts
that current-session snapshot before entering `CONNECTED` and applies a
separate bounded synchronization watchdog. Later Status refreshes register a
waiter bound to the current local connection attempt and session before sending
the request. Transport loss rejects it, and a new connection generation cannot
complete it. No request is replayed.

Selection callbacks and in-flight reads are generation-bound before and after
their asynchronous boundary. Debounced changes during synchronization collapse
into one `design refresh needed` latch. The first authoritative synchronized
snapshot releases exactly one fresh Host-side `design.observe`; no event
history is queued. Disposal cancels debounce state, invalidates the generation,
and clears the latch. Local selection DTOs continue to update presentation
only.

## Retained compatibility dispositions

- `activate()` remains the idempotent startup fallback. Runtime construction
  has one guarded site; `onStartupFinished` and menu fallback share it.
- The V1 interactive endpoint continues to default to `127.0.0.1:49626`.
  Ports 49624 and 49625 retain their separate authority meanings.
- Registration replaces only the stable AIA-owned selection listener ID.
  It neither enumerates nor removes unrelated listeners, and removal remains
  idempotent.

## Frozen boundaries and limitations

No interactive, Evidence, AIA-JLCEDA, Hardware, Harness-Hardware,
teaching-claims, or publication-bridge Schema changed. No selection, operation,
physical, Tool, or execution authority changed. JLCEDA still cannot issue
`TrustedOperationScope` or `ProbeSetupConfirmation`.

The runtime remains process-local with in-memory credentials and no durable
workflow recovery, secure persistence, installer, updater, audit database, or
observability platform. Both real-smoke authorizations are consumed. Another
real smoke requires a separate review and fresh explicit authorization.
