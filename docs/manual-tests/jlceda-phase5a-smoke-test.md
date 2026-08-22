# JLCEDA Phase 5A Manual Smoke Test

The completed 2026-08-23 observation is recorded in
[`jlceda-phase5a-real-runtime-observation-2026-08-23.md`](jlceda-phase5a-real-runtime-observation-2026-08-23.md).
It found that the tested runtime accepted a one-net cross-probe request but did
not render a visible schematic-canvas change, including after clearing the
selected overlay.

This procedure is deliberately excluded from ordinary CI because it requires a
real JLCEDA Pro editor runtime and a human-visible design. It performs no design
mutation and requires no external-interaction permission.

## Preconditions

1. Use JLCEDA Pro V3 with an editor engine compatible with `^3.2.0`.
2. Build the extension with `npm run build` from the repository root.
3. Locate
   `extensions/jlceda/build/dist/ai-instrument-assistant_v0.2.4.eext`.
4. Keep a non-critical schematic available. The preferred scenario is project
   `STM32_Test`, document `main_schematic`, with a selectable `PWM_OUT` wire.

## Enable diagnostic console

1. For the web editor, open `https://pro.lceda.cn/editor?cll=debug`.
2. For the desktop client, follow the official debug-mode instructions.
3. Press F12 three times and select the Console tab.
4. Do not paste or execute any generated JavaScript. The console is observation
   only for this test.

## Import and enable

1. Open **Advanced → Extension Manager** in JLCEDA Pro V3.
2. Click **Import** and select the generated `.eext` file.
3. Enable **AI Instrument Assistant** and enable display in the top menu if the
   editor asks.
4. Do not grant external-interaction/network permission; Phase 5A does not need
   it.
5. Reload the editor if requested.
6. Confirm the console contains one bounded `runtime diagnostics` record with
   editor version, compiled date, environment, edition, and three capability
   booleans. It must not contain the complete `eda` object or user information.

## Inspect current document

1. Open `STM32_Test → main_schematic` and focus its canvas.
2. Select **AI Instrument Assistant → Inspect Current Document**.
3. Confirm a bounded information dialog reports a schematic document.
4. In the console, verify the normalized record contains only provider,
   document ID, normalized document type, project ID, library ID, and a bounded
   raw-shape summary.
5. Verify no tab ID value, primitive object, project contents, or large raw
   object was logged.

## Inspect selection

1. Click empty canvas space and run **Inspect Selection**. Confirm count `0`.
2. Select the `PWM_OUT` wire and run **Inspect Selection** again.
3. Confirm the DTO reports one bounded object with primitive ID, primitive type
   `Wire`, and—if the BETA runtime has refreshed it—net name `PWM_OUT`.
4. Confirm `totalSelected`, `truncated`, and `primitiveTypeSummary` are present.
5. Confirm the console does not expose coordinates, raw primitive methods,
   nested runtime state, or a serialized official object.

## Highlight selection

1. Keep `PWM_OUT` selected.
2. Choose **AI Instrument Assistant → Highlight Selection**.
3. Confirm the selected overlay is cleared before cross-probe highlight is
   applied. Confirm the result dialog reports the resolved target count and either
   `status=applied` or `status=noop`. `applied` means the official API accepted
   the request; visible rendering remains a separate manual observation.
4. Confirm the operation did not create, modify, delete, save, or reselect a
   design object.
5. If the API is unavailable or returns false, capture the bounded error/result
   as a compatibility finding; do not change the Python Domain or add a raw API
   fallback.

## About and negative checks

1. Choose **About** and confirm version `0.2.4`, editor diagnostics, and the
   statement that Backend/WebSocket/Agent/design mutation are absent.
2. Close all design documents and run **Inspect Current Document**; confirm the
   result explicitly reports no active document.
3. Record editor version, client/web environment, capability booleans, observed
   primitive type strings, whether `PWM_OUT` resolved, and highlight outcome.
4. Remove or disable the extension after validation if this is a production
   design environment.
