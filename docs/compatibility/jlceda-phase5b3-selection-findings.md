# JLCEDA Phase 5B.3 Selection Compatibility Findings

## Automated evidence

The frozen `@jlceda/pro-api-types` 0.4.14 boundary and fake official runtime
verify empty, wire, component, unsupported, missing-net, multiple, API failure,
capability-unavailable, and 128-object bound cases. Contract tests verify that
only a finite `SelectionContext` can cross the protocol boundary. Dispatcher
tests verify the document/selection/document observation sequence and rejection
when document identity changes.

These tests do not prove behavior inside a real JLCEDA editor.

## Existing real-runtime observations inherited from Phase 5A

- Both current selection methods are BETA.
- Schematic primitive identity must come from
  `SCH_SelectControl.getAllSelectedPrimitives_PrimitiveId()`; reading identity
  from a selected schematic wire proxy entered a PCB initialization path in the
  observed runtime.
- `ISCH_PrimitiveWire.getState_Net()` can be stale according to official type
  documentation. A network name is therefore limited observed context, not a
  revision or whole-design truth.

## Phase 5B.3b real-runtime status

The user reported that the end-to-end remote `eda.selection.get` smoke test
passed. Empty selection, Wire, Component, multiple selection, and provider
primitive identity/type mapping were confirmed in a real JLCEDA runtime.
Derived nets did not invent endpoints, source, or expectations; no raw primitive
leakage or stale cached selection was observed in those runs.

This is user-executed runtime evidence, separate from fake-runtime and contract
tests. The report does not establish atomic snapshots, freshness under every
race, or highlight behavior. It does not report editor version or archive hash.
See [the manual evidence record](../manual-tests/jlceda-phase5b3b-real-runtime-observation.md)
for the exact scope and unconfirmed cases.
