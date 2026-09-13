# Phase 8.5B — JLCEDA AIA Interaction Surface

Status: **REAL SMOKE NOT PASS / RUNTIME COORDINATION REPAIR UNDER REVIEW**

Date: 2026-09-12

Validation mode: offline fakes and loopback sockets only. Real JLCEDA,
Hardware, VISA, SCPI, DeepSeek, measurement, and EDA mutation were not used.

## 1. Reviewed runtime disposition

Phase 8.5B implements the reviewed Phase 8.5B.0 findings without retaining its
disposable runtime. The production UI disposition is
`OFFICIAL_DIALOG_FALLBACK`; production code has no `createDesignPortal`, HTML,
or script-injection path. The transport disposition is
`SEPARATE_INTERACTIVE_LISTENER_REQUIRED`.

Endpoint ownership is explicit:

| Endpoint | Authority domain |
| --- | --- |
| 127.0.0.1:49624 | frozen AIA-JLCEDA v1 provider gateway |
| 127.0.0.1:49625 | frozen Harness-Hardware v1 backend |
| 127.0.0.1:49626 by default, configurable | AIA Application Host interactive listener |

The interactive port is product configuration, never protocol identity. The
Host rejects remote bind addresses and the two reserved ports. It never kills
an unknown owner of a configured port. The JLCEDA settings adapter persists
only the non-secret port. The independent 32-byte credential is obtained via
the existing password dialog and remains process memory only; the Host loads
its copy through an out-of-band credential reference.

## 2. Transport and authentication

`InteractiveWebSocketServer` is an Application-Host-owned lifecycle adapter.
JLCEDA is client only. Each connection performs independent one-use
`aia-interactive-auth/v1` HMAC challenge/proof, then the exact shared
`aia-interactive/v1` hello negotiation. Authentication is deliberately
separate from AIA-JLCEDA v1: credential, framing, session, correlation,
connection generation, and reconnect state are not shared.

The server sends an authoritative Host snapshot immediately after hello
acceptance. JLCEDA does not enter `CONNECTED` until that snapshot passes the
shared JSON Schema and matches the new session/application generation. Later
events trigger a fresh snapshot request. Reconnect uses bounded 0.5/1/2/5
second delays, unique physical socket IDs, a new HMAC challenge, new frontend
connection generation, and new session. It clears old snapshot/session state
and never queues or replays Challenge answers.

The Host remains final validator for application generation, session,
frontend kind, workflow revision, Challenge ID/nonce/expiry, candidate set,
operation plan, target, channel, and physical statements. Authentication only
permits submission; it grants no selection, Scope, confirmation, execution, or
evidence authority.

## 3. Official Dialog interaction surface

The normal schematic menu is bounded to status, design refresh, selection
resolution, current target, pending action, evidence availability, guarded
highlight, cancellation, interactive/provider connection configuration,
disconnect/reconnect, and About. Developer probe/report actions are absent.

The status dialog uses the Host snapshot and an allowlisted product projection.
It excludes ports, PIDs, UUIDs, sessions, secrets, paths, provider payloads,
VISA/SCPI, serials, waveform arrays, and model output. Because the current
shared snapshot carries bounded workflow/status rather than rich target or
evidence DTOs, JLCEDA V1 truthfully shows workflow labels and availability; it
does not invent measurement values or evidence details.

Design-selection options use the exact Host-issued candidate identity as the
hidden option value. Display text is presentation only. A reordered list or
duplicate display name cannot change the returned identity. The current
interactive contract does not carry Host-approved candidate labels, so V1
uses generic candidate labels rather than guessing `Wire — PWM_OUT` bindings.
Adding rich labels would require a separately reviewed additive protocol
projection.

Phase 8.5B intentionally does not expose operation authorization or physical
confirmation as JLCEDA production authority paths. When either pending action
appears, the extension gives a static bounded instruction to continue in the
DeepSeek Harness and sends no Challenge answer. The existing
`TrustedOperationScope` and `ProbeSetupConfirmation` production factories stay
in that TypeScript runtime for Phase 8.5C; no replacement Python factory or
cross-runtime authority bridge is introduced. No measurement command exists
in the JLCEDA surface.

Cancellation is workflow/revision-bound. It withdraws pending interaction via
the Host and does not imply rollback, refund, replay, or execution. Highlight
reuses only the existing `view.highlight` application command and guarded
AIA-JLCEDA semantic path. Provider acceptance remains unverified rendering,
not evidence or authority.

## 4. Selection observer

One static schematic mouse listener is registered per activation-owned product
runtime. Registration replaces only the stable AIA-owned identifier left by a
prior extension generation. Notifications are debounced/coalesced,
their payload is ignored, and the existing `JlcEdaApiAdapter` performs a fresh
bounded selection read. The local result may update presentation only; the
`design.observe` command asks the Host/application integration to re-observe
through its provider path. The extension never creates domain evidence from
the event or local DTO.

Callbacks, in-flight presentation reads, and debounce work are generation-bound.
A change during connection synchronization becomes one current-state refresh
latch and produces one fresh Host observation after the authoritative snapshot;
historical selection events are never queued or replayed. Disposal clears the
debounce timer, removes the listener idempotently, stops
the client, zeroes its private credential copy, and clears
presentation/session state. Module fields retain only transport and
presentation state. Every product action refreshes the Host
snapshot before acting, and the Host rejects stale state. Cross-menu lifecycle
behavior in the real JLCEDA host remains a required later smoke-test item; no
module cache is treated as authority.

## 5. Error and permission UX

Missing external-interaction capability is translated to an official bounded
Retry/Cancel dialog with local permission guidance. Raw WebSocket/provider
exceptions are never displayed. Stable Host/product codes map to fixed short
messages for unavailable Host, incompatible version, authentication failure,
ambiguous/stale selection, authorization or physical confirmation required,
stale confirmation, instrument unavailable/disconnected, and cancellation.

## 6. Test and security result

Shared interactive Python/TypeScript fixture tests remain the wire-shape
authority. New fake tests cover endpoint collisions, credential reference,
HMAC replay, real loopback handshake/reconnect, new sessions, wrong frontend,
snapshot-before-connected, permission failure, reconnect cleanup, status,
Dialog identity separation, candidate-set staleness, forged choice,
operation/physical Harness deferral with zero answer, cancellation, selection debounce,
fresh read, listener disposal, and non-secret settings.

AST/dependency tests prove the JLCEDA interaction package imports no Hardware,
VISA, SCPI, DeepSeek, Agent, `TrustedOperationScope`,
`ProbeSetupConfirmation`, or execute command. All official `eda.*` access
remains in `JlcEdaApiAdapter`. Production source has no portal dependency,
spike/v0 auth, dynamic script execution, raw method dispatch, arbitrary HTML,
or design mutation.

No canonical Evidence v1, AIA-JLCEDA v1, Hardware, or Harness-Hardware Schema
semantics changed. `aia-interactive/v1` remains the exact Phase 8.5A contract.

## 7. Bounded limitations and review gate

- Host workflow/Challenge/audit state remains process-local and non-durable.
- The extension does not persist its credential; configuration is required
  again after a lifecycle that loses runtime memory.
- The current protocol has no rich candidate-label, ProbeTarget-detail, or
  numeric EvidenceSummary projection. The UI therefore fails closed to generic
  truthful wording.
- The minimal production composition now instantiates the interactive server,
  Host, async Actions Adapter, provider-neutral EDA path, and separate
  AIA-JLCEDA gateway. A normal-user launcher/installer, protected credential
  provisioning, single-instance OS integration, and durable settings remain
  later product-hardening work.
- Official select/input APIs remain capability-detected; real cross-menu
  lifecycle and permission UX require a separately approved read/UI smoke.
- Highlight acceptance still does not prove visible highlight.
- JLCEDA is not a chat or independent LLM surface.

Phase 8.5B remains **REAL JLCEDA SMOKE NOT PASS / RUNTIME COORDINATION REPAIR
UNDER REVIEW**. See
[Phase 8.5B.1 Runtime Composition Remediation](phase8_5b1-runtime-composition-remediation.md).
The first failed real-smoke authorization was consumed. See
[Interactive Runtime Coordination Repair](phase8_5b2-interactive-runtime-coordination-repair.md).
The repaired implementation was approved, but separately authorized real
Attempt 2 also ended NOT PASS at Status client completion. No further real
JLCEDA retry is authorized. Phase 8.5C has not started.
