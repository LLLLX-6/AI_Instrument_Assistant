# Phase 8.5B — Real JLCEDA Design Smoke Attempt 4

Status: **NOT PASS — SELECTION EVENT DID NOT PRODUCE A FRESH HOST OBSERVATION**

Date: 2026-09-13

This record covers the single explicitly authorized, bounded Attempt 4,
targeting the reviewed v0.2.23 menu-runtime bridge artifact. Attempts 1–3
remain unchanged and historical. The run used the production Python
composition with separate provider and interactive listeners. No automatic
retry, production patch, EDA write, Hardware action, VISA/SCPI operation, or
DeepSeek request was allowed. The active editor-side semantic version was not
independently captured through About or another bounded product identity
surface and is therefore recorded as unverified rather than inferred from the
filesystem artifact.

## Status boundary result

The production Host started successfully with the provider listener on
`49624`, the interactive listener on `49626`, Hardware inactive, and the
workflow in `OBSERVING_DESIGN`. After a fresh JLCEDA launch and connection, the
user invoked Status exactly once. The normal product Status Dialog rendered
and reported:

- Application Host: `READY`
- Workflow: `OBSERVING_DESIGN`
- Design selection authority: available
- Current selection: not observed
- Hardware: unavailable

No diagnostic UI and no false Host-unavailable message appeared. This proves
that the active build's private menu bridge reached the activation-owned
runtime and completed the authoritative Host snapshot path for Status; it does
not independently prove the active semantic version.

## Design observation result

The user invoked Refresh Design Context once and then selected the real
`PWM_OUT` wire/network object. The Host recorded exactly one fresh observation
and advanced the workflow from revision 1 to revision 2 with state
`DESIGN_CONTEXT_READY`. That observation contained zero selection candidates,
no typed candidate binding, no trusted design decision, and no ProbeTarget.

After the user reselected the object, no subsequent Host workflow-state event
or fresh observation was observed. Therefore the real selection event did not
complete the required path to a new authoritative Host observation. The run
was stopped under the approved fail-fast/no-retry rule. A second refresh,
reconnect, reload, patch, trusted disambiguation, or target resolution was not
attempted.

## Bounded observed results

| Observation | Count/result |
| --- | ---: |
| Production Host startup | 1 |
| Normal Status Dialog success | 1 |
| False Host-unavailable Status | 0 |
| Host-side fresh observations | 1 |
| Final observed Host revision | 2 |
| Final observed workflow state | `DESIGN_CONTEXT_READY` |
| Selection candidates | 0 |
| Typed candidate bindings | 0 |
| Trusted design-selection decisions | 0 |
| ProbeTargets | 0 |
| Automatic retries | 0 |
| EDA design writes | 0 |
| Hardware executions | 0 |
| VISA sessions | 0 |
| SCPI operations | 0 |
| DeepSeek requests | 0 |

Stop-time aggregate counters were not emitted by the runner after the bounded
interrupt. Counts not directly observed above are not reconstructed. No real
provider identifiers or missing selection details are invented.

## Security and compatibility result

The real run was read-only. It did not create operation authority, physical
confirmation, Hardware authority, or model authority. This record contains no
credential, HMAC proof, raw frame, raw provider payload, unrestricted design
identifier, local absolute path, VISA resource, instrument serial, waveform,
exception stack, or model output. No protocol Schema was changed.

The menu-runtime bridge repair is validated for Status. The remaining failure
is bounded to the real selection-event/authoritative-observation path after a
successful initial refresh; no narrower cause is claimed from the available
evidence.

## Conclusion

Attempt 4 is **NOT PASS**. Status crossed the production menu bridge and Host
snapshot boundary successfully, but a real `PWM_OUT` reselection did not
produce the fresh authoritative observation required for typed candidate
binding and ProbeTarget creation. Phase 8.5B remains under review. This
Attempt 4 authorization is consumed; any further real execution requires new
review and fresh explicit authorization.
