# Phase 8.5B.1 — Minimal Runtime Composition Remediation

Status: **PRODUCTION COMPOSITION REVIEWED; LATER REAL SMOKE NOT PASS**

Date: 2026-09-12

Validation mode: offline tests and ephemeral loopback sockets only. No real
JLCEDA, EDA read, EDA write, Hardware, VISA, SCPI, or DeepSeek execution was
performed.

## Production composition

The missing production glue is now explicit:

```text
JLCEDA interaction client
  -> aia-interactive/v1 InteractiveWebSocketServer
  -> async InteractiveGateway
  -> ProductionInteractiveApplicationActions
  -> ApplicationHost + provider-neutral EDA application service
  -> EDAInterface
  -> AIA-JLCEDA v1 LocalWebSocketGateway
  -> fresh JLCEDA provider observation
```

`compose_jlceda_interactive_host()` creates this path with separate provider
and interactive credentials and listeners. Port 49624 remains AIA-JLCEDA v1,
49625 remains Hardware-only, and the configurable interactive endpoint
defaults to 49626. The production composition creates the Python
design-selection issuer; it never substitutes a Fake authority. Hardware, AgentLoop,
VISA, SCPI, and DeepSeek are not composed in this phase.

## Async and coherence boundary

`InteractiveApplicationActions`, `InteractiveGateway.handle_command()`, and
WebSocket dispatch propagate async provider work directly. There is no nested
event loop, synchronous remote wrapper, or fire-and-forget EDA work.

For `design.observe`, the Host captures application generation, workflow ID,
workflow revision, and request correlation under its mutation lock. The lock
is released before awaiting the EDA application service. On return, one guarded
commit revalidates every captured field. A changed generation, missing
workflow, newer revision, or superseded request discards the result as stale;
it cannot overwrite newer Host state. Provider unavailability, timeout, or
failure commits no invented observation and returns only a bounded product
error. The frontend's local fresh DTO remains presentation-only.

## Production TrustedDecisionIssuer composition repair

Preflight found that the original generic `TrustedDecisionIssuer` abstraction
was broader than the real runtime topology. It has been replaced by separated
internal capabilities. Phase 8.5B composes only
`ProductionDesignSelectionDecisionIssuer`, which delegates to the existing
`issue_trusted_design_selection_decision()` and resolution services. The Host
retains the complete typed `DesignSelectionCandidateSetBinding`, exact
candidate identity, selection context, and derived `ProbeTarget`; the wire
still exposes only bounded opaque choice tokens.

`TrustedOperationScope` and `ProbeSetupConfirmation` production factories
remain in the Harness TypeScript runtime and are deferred to Phase 8.5C. The
JLCEDA UI does not answer those Challenges and instead directs the user to
continue in Harness. No Python/TypeScript authority bridge, duplicate factory,
Fake authority, or protocol field was added.

## Runtime and authority ownership

Extension activation now creates one `JlcEdaInteractionRuntime`; menu callbacks
reference that activation-owned instance and deactivation disposes it. The
selection observer, connection, timers, snapshot, presentation cache, and
in-memory credential share this lifecycle. Disposal stops the client and
zeroes its private credential copy. Only the non-secret port may persist.

Design-selection Challenge answers travel through the production server and
gateway to `ApplicationHost`, then to the existing Python trusted selection
factory. The extension cannot create that decision, reconstruct an identity
from a label, change budgets, or skip gates. Cancellation and guarded highlight
reuse their existing Host and EDA application boundaries.

## Validation and bounded limitations

The production-composition integration test uses the real composition factory,
production WebSocket server, gateway, actions adapter, and Host while replacing
only the external EDA port with an async fake. It proves authentication, hello,
one authoritative observation call, Host update, Challenge routing, and zero
execution. Delayed-EDA tests prove no lock is held across await and stale
results cannot create authority. Failure tests cover unavailable, timeout, and
connection loss without provider payload or stack disclosure.

V1 remains intentionally process-local. It has no durable workflow recovery,
audit database, secure credential persistence, installer/updater, Job Object,
rich metrics, or full restart recovery. Host restart may invalidate workflows.
The first real JLCEDA smoke authorization was later consumed. That smoke proved
the production composition but remains historical NOT PASS because of runtime
coordination defects. The separate offline repair is documented in
[Phase 8.5B Interactive Runtime Coordination Repair](phase8_5b2-interactive-runtime-coordination-repair.md).
The approved coordination repair and separately authorized Attempt 2 are
documented by the linked repair and validation records. Attempt 2 is NOT PASS;
another retry is not authorized. Phase 8.5C has not started.
