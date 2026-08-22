# JLCEDA Phase 5A Real-Runtime Observation — 2026-08-23

## Record status

- Evidence type: user-executed manual smoke test in a real JLCEDA Pro editor.
- Extension under test: AI Instrument Assistant Phase 5A builds 0.2.1–0.2.4.
- Recorded by: project development session.
- Editor version, compiled date, client/web environment, project identity, and
  document identity: not captured; this record does not infer them.
- Scope: local extension runtime only. No Python Backend, WebSocket, Agent,
  instrument connection, or design mutation was involved.

This document separates direct editor observations from automated evidence and
engineering conclusions. It must not be represented as an automated end-to-end
test.

## Direct real-editor observations

| Build | Operation | Direct observation |
| --- | --- | --- |
| 0.2.1 | Inspect Current Document | With the schematic canvas focused, the information dialog opened normally. This confirmed that the packaged menu handler was callable after adopting the SDK-required IIFE runtime export. |
| 0.2.1 | Inspect Selection on a schematic wire | The editor raised: `对象未在 PCB 画布初始化，不存在 PrimitiveId。` |
| 0.2.2 | Inspect Selection on a schematic wire | The preceding PrimitiveId error no longer occurred after identity retrieval moved from the primitive proxy to `SCH_SelectControl.getAllSelectedPrimitives_PrimitiveId()`. The user explicitly confirmed that the previous issue was resolved. |
| 0.2.3 | Highlight Selection | No visible canvas highlight was observed. The dialog reported `status=applied`, `componentCount=0`, `pinCount=0`, and `netCount=1`. |
| 0.2.4 | Highlight Selection after clearing the selected overlay | The view still showed no visible change. The dialog again reported `status=applied`, `componentCount=0`, `pinCount=0`, and `netCount=1`. |

The exact 0.2.4 result reported by the real editor was:

```json
{
  "status": "applied",
  "componentCount": 0,
  "pinCount": 0,
  "netCount": 1,
  "warnings": [
    "Official API accepted the request after clearing the selected overlay; visual rendering cannot be verified through the API."
  ]
}
```

## Facts established by the observation

1. The extension package and static menu dispatch are functional in the tested
   editor runtime.
2. Active-document inspection can produce a bounded, human-visible result.
3. A schematic primitive proxy can expose an unusable
   `getState_PrimitiveId()` path that raises a PCB-canvas initialization error.
4. Reading selected primitive identity through the selection-control API avoids
   that observed error.
5. The highlight adapter resolved one semantic net target and the official
   cross-probe call returned a truthy success result.
6. No visible highlight was observed, both while the selected overlay existed
   and after the adapter explicitly cleared that overlay before cross-probe.
7. The tested API surface provides no highlight read-back that could verify
   whether a visual effect was rendered.

## Automated evidence at the end of the observation cycle

- Python Phase 1–4 suite: 60 tests passed.
- Shared TypeScript contract suite: 11 tests passed.
- TypeScript adapter and architecture suite: 18 tests passed.
- Extension 0.2.4 typecheck and package build: passed.
- Generated artifact:
  `extensions/jlceda/build/dist/ai-instrument-assistant_v0.2.4.eext`.

Automated tests verify adapter control flow, bounded DTOs, async-result handling,
selection restoration on failure, dependency boundaries, and the prohibition of
dynamic execution and design mutation. They cannot verify pixels rendered by
the proprietary editor.

## Compatibility classification

For the tested, unidentified real-editor runtime:

- `document.read`: manually observed as working.
- `selection.read`: manually observed as working after the PrimitiveId
  compatibility correction.
- `view.highlight`: API entry point available, request accepted, visual behavior
  unverified and manually observed as ineffective for the tested schematic-net
  scenario.

`view.highlight` must therefore not be advertised as a reliable applied
capability for this runtime. The appropriate classification is
`available-but-behaviorally-unverified` (degraded), not globally unsupported:
the test did not cover every editor version, document type, or cross-document
configuration.

## Engineering decision

Phase 5A will not simulate highlight by changing wire color or other design
properties. It will not claim that an API success boolean proves a visible
effect. Further work on visual feedback requires either a future verified
official API or a separately reviewed semantic fallback. This finding does not
change the provider-neutral Python Domain or the JLCEDA wire protocol.

