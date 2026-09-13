# Phase 8.5B JLCEDA Menu Runtime Bridge

Status: **REAL-RUNTIME MENU BRIDGE REPAIR UNDER REVIEW**

## Confirmed compatibility finding

Real JLCEDA showed that extension activation and exported header-menu functions
may execute in distinct VM/module contexts. A menu function therefore cannot
interpret absent module-local activation state as evidence that the Python Host
is unavailable. Real runtime diagnostics also established that the official
private `SYS_MessageBus` can call from the menu VM into the connected activation
VM.

## Production repair

Runtime-dependent menu exports are now thin invocation stubs. They send one
closed internal command through the fixed private topic `aia.runtime.command`.
Only the activation-owned runtime with an `InteractiveClient` that has reached
`CONNECTED` registers the service. Registration is idempotent and does not rely
on duplicate-topic precedence or broad private-bus removal.

The service uses an explicit action allowlist and static switch to existing
runtime operations. It carries no credentials, sessions, provider/Host
payloads, IDs, authority objects, executable code, or raw frames. The existing
Runtime remains the sole owner of connection/session state and product
presentation. Configure Connection remains the proven bootstrap path.

Offline production loopback proves Status and `design.observe` across the
private bridge, production TypeScript client, Python interactive server, and
ApplicationHost. Stale/disposed owners fail closed. A normal disconnect retains
the same service so that the same owner may reconnect; no second client is
created.

## Preserved boundaries and limitations

No external protocol, Host authority, design-selection authority, Hardware
authority, timeout, or EDA write behavior changed. Operation authorization and
physical confirmation remain deferred to Harness. The JLCEDA host exception
that uses WebSocket close code `0` while disabling an extension remains a host
compatibility limitation and is not repaired here. Historical real smoke
Attempts 1–3 remain NOT PASS. Attempt 4 requires new review and authorization.
