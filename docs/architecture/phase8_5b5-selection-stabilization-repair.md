# Phase 8.5B Selection Stabilization Compatibility Repair

Status: **CLOSED FOR NOW / LIMITED INTEGRATION**

## Confirmed real-runtime finding

In the authenticated Provider Adapter context, the canonical
`getAllSelectedPrimitives()` call succeeded with two selected objects when the
selection was stable. The ID API also returned two values, but bulk resolution
returned only one `Wire`; ID reconstruction is therefore not equivalent to the
canonical object read and is not a production fallback. The earlier
`undefined.forEach` host failure is bounded as transient/state-sensitive rather
than a permanent Provider-VM capability failure.

## Production control flow before repair

The selection event carried no evidence and armed a generation-local 150 ms
debounce. At the debounce callback, the extension first emitted the
authoritative `design.observe` command and then immediately started a separate
presentation-only selection read. Those two paths could enter the same JLCEDA
selection API concurrently. Presentation failure was swallowed and did not
logically cancel the Host command, but the presentation read could still
disturb the Provider read. Repeated events within the debounce coalesced. The
Python interactive server admitted at most one command task per connection,
and the Host generation/revision guard rejected stale remote results, so
Provider operations could not overwrite a newer Host revision.

## Narrow repair

The selection listener now performs trigger/latch work only. After the existing
150 ms stabilization boundary it emits one authoritative Host refresh and does
not perform a local selection read. Presentation state may remain unavailable;
it is never a prerequisite for evidence. The existing generation-local latch
now records the workflow revision of an in-flight observation. Further events
coalesce into one pending refresh, which is released only after a Host snapshot
shows that revision has advanced; it never creates an overlapping Provider
operation. Manual Refresh enters this same latch and the same
`InteractionSurface.refreshDesignContext()` command path.

The Provider keeps `getAllSelectedPrimitives()` as its canonical object read,
followed by the existing identity read and exact count guard. Because the real
failure occurred despite the existing debounce, one bounded read-only retry is
allowed after one event-loop turn. There are at most two complete observation
attempts, no loop beyond that bound, no polling/backoff, and a second failure
returns the existing bounded `provider_error`. The diagnostic A/C/D menu and
its diagnostic RPC/service code are removed from the production artifact.

## Preserved boundaries

No EDA write, protocol, domain, authority, WebSocket ownership, trusted
selection, Operation Scope, Physical Confirmation, Hardware, VISA/SCPI, model,
or later-phase behavior changed. Attempts 1–4 and the diagnostic history remain
historical evidence. This offline repair does not itself establish a real
runtime PASS.

## Final disposition

Phase 8.5B is closed for now as a limited integration. The retained working
surface is extension activation, Provider and Interactive connections,
ApplicationHost integration, the private cross-VM MessageBus command bridge,
Status, manual Refresh, read-only EDA integration, and the bounded
stabilization controls described above.

Reliable automatic current JLCEDA UI-selection capture remains
host-state-sensitive in the reviewed JLCEDA 3.x runtime. It is explicitly
deferred and no longer blocks the product roadmap. Typed candidate binding
originating from that capture, trusted design selection depending on it, and
automatic `ProbeTarget` derivation from it are deferred with it. Reconsidering
them requires a later reviewed product need and a demonstrably more reliable
integration mechanism; this document proposes no further repair.
