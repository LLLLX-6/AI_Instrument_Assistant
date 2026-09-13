# Phase 8.5B — Interactive Client Completion Boundary Repair

Status: **OFFLINE IMPLEMENTATION REVIEWED PASS / REAL ATTEMPT 3 NOT PASS**

Date: 2026-09-13

Both real Phase 8.5B smoke attempts remain historical **NOT PASS**. Attempt 2
proved that an explicit Status request reached the production Python Host and
that one `workflow_snapshot` reply was sent, but the available runner did not
contain client-side counters. This repair used only offline unit tests and
ephemeral loopback sockets; it does not reinterpret missing real evidence.

## Client completion defect

The TypeScript snapshot ingestion path accepted and stored a valid snapshot,
then invoked the non-authoritative `onSnapshot` observer before completing the
pending explicit Status waiter. An observer exception could therefore strand
the waiter even though transport delivery, parsing, Schema validation, and
session validation had succeeded. The waiter later surfaced as the same
generic Host-unavailable failure used by transport, validation, session, and
Dialog failures.

The exact observer exception was not recorded by Attempt 2, so this document
does not claim that missing historical value. A deterministic Red test proves
that the reviewed ordering defect produces the same bounded failure shape.

## Repair and V1 semantics

One workflow-snapshot ingestion path serves both initial synchronization and
explicit Status refresh. It now:

1. observes and parses the frame;
2. validates the frozen interactive/v1 Schema;
3. verifies the current connection attempt and authenticated session;
4. updates the current authoritative snapshot;
5. completes the matching explicit waiter, if present;
6. invokes the non-authoritative state observer under a bounded failure guard.

At most one explicit current-snapshot waiter may exist per active session. A
second request fails with `SNAPSHOT_WAITER_ALREADY_PENDING` and cannot replace
the first. The next valid same-session workflow snapshot may satisfy that
waiter, including an unsolicited current-state snapshot. Old-attempt and
old-session frames cannot satisfy it. One three-second client timer owns the
explicit request timeout; the Status layer adds no competing timeout.

Bounded categories distinguish transport timeout/unavailability, invalid
frame, session mismatch, an already-pending waiter, and Status presentation
failure. Diagnostics contain counts only: callback receipt, JSON and Schema
success, workflow-snapshot frames, attempt/session rejection, waiter
registration/presence/absence/resolution/timeout, observer failure, Status
snapshot resolution, and Dialog invocation result. No raw frame, Snapshot,
identifier, credential, HMAC material, path, or exception is logged.

## Offline production proof

A production TypeScript `InteractiveClient` was connected through a Node
loopback transport to the production Python composition and
`InteractiveWebSocketServer`. Only the outbound provider-neutral EDA Port was
an in-memory test dependency. The production Snapshot projector and dispatcher
were not replaced. Authentication, hello, initial synchronization, explicit
Status request/reply, waiter completion, bounded projection, and presentation
adapter invocation completed successfully.

The repaired extension package version is v0.2.17 so a future authorized
Attempt 3 cannot be confused with the v0.2.16 artifact used by Attempt 2.

## Frozen boundaries and limitations

ApplicationHost, Gateway, Python WebSocket request handling, production
Actions, EDA observation, trusted issuers, authentication, authority split,
and all protocol Schemas are unchanged. Selection/reload coordination was not
modified. Official JLCEDA callback delivery and actual Dialog rendering
remained real-runtime uncertainties after the offline review. Separately
authorized Attempt 3 stopped at Gate A: the server sent one initial snapshot,
but the explicit Status action produced zero server-side snapshot requests and
replies. That result does not invalidate the offline proof, but it leaves Phase
8.5B real-runtime incomplete. Attempts 1, 2, and 3 are consumed. Phase 8.5C has
not started.
