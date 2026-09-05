# JLCEDA Phase 5B.2b Real-Runtime Observation — 2026-09-05

## Scope

This record covers the real JLCEDA Pro runtime path for the single authenticated
operation `eda.document.get_active`. It does not cover remote selection,
highlight, EDA mutation, Agent, LLM or instrument access.

## Environment and evidence boundary

- Extension package: AI Instrument Assistant v0.2.8
- Transport: authenticated localhost WebSocket on `127.0.0.1:49624`
- Observation source: manual test performed in the real JLCEDA Pro host
- Result source: operator-observed runtime behavior, not an automated fake
- Sensitive document UUIDs and the shared secret are intentionally not recorded

## Actual JLCEDA runtime results

| Check | Result | Observation |
|---|---|---|
| Active document read | PASS | Python received a normalized active document through the complete remote path. |
| Provider/document identity | PASS | Provider and official document identity were preserved. |
| No fabricated metadata | PASS | Unavailable names, revision, fingerprint and dirty state remained explicitly unknown. |
| Switch active document | PASS | Reading after a document switch returned the new document identity. |
| No stale cache | PASS | The previous document observation was not returned after switching documents. |
| No active document | PASS | The no-document condition followed the explicit structured error path. |

## Separation from automatic tests

Automatic tests validate schemas, correlation, session ownership, timeout,
disconnect handling, DTO cropping, mapping and architecture dependencies using
controlled test peers. The observations above separately confirm the real host
behavior and are not inferred from those automatic tests.

## Acceptance

Phase 5B.2b is accepted for its intended read-only active-document vertical
slice. This result does not authorize remote selection or highlight behavior.
