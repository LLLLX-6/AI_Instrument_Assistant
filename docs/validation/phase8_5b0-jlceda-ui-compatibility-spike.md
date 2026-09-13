# Phase 8.5B.0 — Real JLCEDA UI Compatibility Spike

Status: **PASS — COMPATIBILITY SPIKE REVIEWED**

Date: 2026-09-12

This record covers a bounded real JLCEDA read/UI-only compatibility spike. It
is not the Phase 8.5B product implementation and grants no authority for EDA
writes, Hardware, VISA, measurement, or model execution.

## Runtime and package baseline

The real bounded diagnostic reported:

- JLCEDA editor `3.2.149.88089769`;
- editor compiled-date string `06/03/2026`; its format was not stated, so the
  provider string is preserved without reinterpretation;
- desktop client, JLCEDA Professional edition;
- extension engine compatibility `^3.2.0`;
- frozen repository SDK compatibility pro-api-sdk `1.6.17`;
- installed `@jlceda/pro-api-types 0.4.14`;
- Node `24.18.0`, npm `11.16.0`;
- disposable probe package `0.0.4`.

The bounded diagnostics do not expose the loaded API bundle build ID. Earlier
historical module URLs are not promoted to current evidence.

## UI capability result

Runtime capability observation was:

```text
createDesignPortal       false
informationDialog        true
confirmationDialog       true
selectDialog             true
selectionEvent           true
```

The guarded portal path failed with `createDesignPortal_unavailable`; no
portal was created. Modeless behavior, portal re-render, and portal
close/reopen therefore could not be validated and are not claimed.

The official information, confirmation, and select dialogs rendered and their
bounded callbacks completed. The selected UI disposition is:

```text
OFFICIAL_DIALOG_FALLBACK
```

Phase 8.5B must not depend on `createDesignPortal` for this runtime. Any richer
persistent view belongs to a separately reviewed Harness/AIA surface, not
injected HTML or script.

## Selection event and lifecycle result

The extension registered a schematic selection listener under a static ID.
After an event it ignored the event payload, coalesced the notification,
removed the listener, and performed a fresh bounded read through the existing
`JlcEdaApiAdapter`. The user observed `Wire — PWM_OUT`.

The cleanup check reported that no probe listener remained. Repeating the
one-shot probe produced one result, not duplicate callbacks. This validates
registration, event observation, fresh read, one-shot disposal, and repeat
use. Extension-reload cleanup was not separately exercised.

Separate menu invocations did not retain module-memory counters. Phase 8.5B
must keep authoritative interaction state in the Python Host and treat
extension module memory as disposable.

## Transport result

The production AIA-JLCEDA listener on 49624 is protocol-specific and does not
route by WebSocket path. Its TypeScript boundary also accepts only an explicit
`ws://127.0.0.1:<port>` endpoint, not a path. Phase 8.5A intentionally provides
no interactive socket implementation. Shared-listener path multiplexing and a
second logical endpoint in the existing gateway are therefore neither
implemented nor proven.

The spike used a temporary separate listener on 49625. This is a fixture, not
an approved production port. It used a separate ignored secret and isolated
HMAC pre-auth framing before the canonical `aia-interactive/v1` hello. The
secret was not placed in the URL, UI report, logs, or repository.

The real sequence was:

```text
Connected -> Reconnecting -> Connected
```

The server forced one bounded transport loss after the first accepted hello.
The extension created a new physical WebSocket attempt, repeated pre-auth,
sent a new hello, and received another accepted acknowledgement. The same Host
process retained its application generation; its second `connect_frontend`
call created a new connection generation and session. No Challenge was
submitted, and the spike issuer rejects every authority-issuance method.

The selected transport disposition is:

```text
SEPARATE_INTERACTIVE_LISTENER_REQUIRED
```

This does not approve the spike framing or port as production contracts. Phase
8.5B must review the durable socket/authentication binding and stable endpoint
configuration. A shared process may own both listeners, but protocol identity,
credentials, sessions, negotiation, and authority remain separate.

The new extension UUID initially lacked JLCEDA external-interaction permission,
so no connection reached the listener. Enabling that permission made the real
connection and reconnect succeed. Product onboarding must surface this
provider requirement without exposing credentials.

## Failure and compatibility findings

- Host absent produced no EDA or external side effect.
- Host available after extension startup was reachable after retry/configure.
- Forced transport loss produced a bounded successful reconnect.
- Incompatible and wrong-generation messages remain fail-closed in Phase 8.5A
  tests; they were not injected into the real runtime.
- Port collision is a startup failure; no existing process was terminated and
  no authority domain was silently changed.
- Portal absence safely fell back to official dialogs.
- Existing AIA-JLCEDA production source and canonical contract were unchanged.

## Bounded execution counts

| Operation | Count |
| --- | ---: |
| Authenticated interactive JLCEDA connections | 2 |
| Fresh bounded EDA selection reads | 2 |
| EDA writes | 0 |
| Hardware executions | 0 |
| VISA sessions | 0 |
| DeepSeek requests | 0 |
| Challenge answers | 0 |
| Trusted authority issuances | 0 |

The two reads were the initial and repeated one-shot selection-event probes.
No raw provider payload or design identity is retained here.

## Security result

The disposable extension uses statically named official dialog,
selection-event, selection-read, and WebSocket methods. It contains no `eval`,
`new Function`, arbitrary method dispatch, backend-supplied code, injected
HTML, raw EDA operation dispatcher, or design mutation API. Status projections
are bounded labels; display names are not identity.

The real test used no Hardware, VISA, SCPI, measurement, DeepSeek, highlight,
or EDA write. Ignored secrets and transient build/log files remain outside
version control.

## Spike-code disposition

Potentially reusable findings and patterns are the official dialog fallback,
event-to-debounced-fresh-read flow, static listener cleanup, permission
onboarding, separate listener/authentication authority, and unique reconnect
attempt IDs.

Delete or replace before Phase 8.5B completion: the portal component tree, the
temporary 49625 endpoint, spike-only authentication framing and no-authority
issuer, manual report counters/menus, and disposable manifest/build target.

## Bounded conclusion

The spike passes its compatibility purpose. It rejects the proposed modeless
portal on the tested runtime, proves the official dialog fallback, proves
selection-event-to-fresh-read behavior, and proves authenticated reconnect on
a separate Host listener. It does not prove a full Phase 8.5B user experience
or production transport.
