# Phase 8.5B — Real JLCEDA Design Smoke

Status: **NOT PASS — INTERACTIVE RUNTIME COORDINATION BLOCKER**

Date: 2026-09-12

This record covers the single authorized bounded Phase 8.5B real JLCEDA
design-side smoke. It does not authorize or record EDA writes, Hardware,
VISA, SCPI, measurement, DeepSeek, or Phase 8.5C execution.

## Proven production path

- The reviewed Python production composition started with separate provider
  (`49624`) and interactive (`49626`) loopback listeners. The Hardware listener
  remained inactive.
- The production `ProductionDesignSelectionDecisionIssuer` was composed; no
  fake authority was installed.
- Real JLCEDA Pro `3.2.149.88089769` authenticated independently to both the
  AIA-JLCEDA provider listener and the interactive listener.
- Interactive `CONNECTED` was emitted only after authentication, hello
  acceptance, and an authoritative Host snapshot.
- During the first bounded selection attempt, the Host recorded one fresh
  observation containing two typed candidates and entered
  `WAITING_FOR_DESIGN_SELECTION`.
- A following observation recorded an empty current selection and moved the
  same workflow to `DESIGN_CONTEXT_READY`. The bounded Host observation count
  reached two. Raw provider payloads and real object identifiers were not
  retained in this record.

## Real compatibility findings

1. The tested locally imported extension did not reliably receive its declared
   `onStartupFinished` activation callback. A menu fallback now invokes the
   same idempotent `activate()` entry; runtime construction remains located
   only in `activate()` and cleanup remains in `deactivate()`.
2. The official numeric input Dialog did not reliably invoke the continuation
   needed to open a second password Dialog. Interactive V1 therefore uses its
   existing validated/persisted port, defaulting to `49626`, and presents one
   password Dialog.
3. Extension reload did not reliably dispose the prior selection listener.
   The adapter now replaces only its own fixed listener ID before registering
   the current activation callback. Event payloads remain non-authoritative.
4. The first selection event and a manual `Refresh Design Context` overlapped.
   The Host preserved its revision guards, but the later observation replaced
   the pending typed selection with the then-current empty selection. A stale
   follow-up caused the interactive session to disconnect safely.
5. After reconnect and extension reload, the real interactive connection again
   authenticated and remained TCP-connected, but `Status` could not obtain a
   current snapshot within its bounded wait and reported Host unavailable.
   A subsequent real selection change produced no new Host observation.

## Unmet PASS criteria

- Status UI was not reliably available across the real cross-menu flow.
- The final reloaded selection event did not reach the Host-side fresh-read
  path.
- The issued design-selection Challenge was not validly answered.
- No trusted design-selection decision was issued.
- No `ProbeTarget` was resolved.
- Replay/stale-answer, cancellation, guarded highlight, and completed reload
  lifecycle proofs were not performed.

The narrow blocker is interactive snapshot/command/selection-event coordination
across real menu actions and reload. Further real retries are prohibited until
that behavior receives a separate architecture review.

## Bounded observed counts

| Observation | Count/result |
| --- | ---: |
| Host-side fresh design observations | 2 |
| Typed candidate bindings observed | 1 |
| Candidate count in that binding | 2 |
| Trusted design decisions | 0 |
| Resolved ProbeTargets | 0 |
| Operation authorization answers | 0 |
| Physical confirmation answers | 0 |
| EDA writes | 0 |
| Hardware executions | 0 |
| VISA sessions | 0 |
| SCPI operations | 0 |
| DeepSeek requests | 0 |

Selection-event, connection, reconnect, and provider-read call counts that were
not durably captured are intentionally not reconstructed.

## Security and protocol result

No credential, HMAC proof, raw provider payload, unrestricted real identifier,
absolute host path, VISA resource, instrument serial, waveform, exception stack,
or model output is included. Evidence v1, AIA-JLCEDA v1, Hardware canonical,
Harness-Hardware v1, teaching-claims/v1, and aia-interactive/v1 schemas were not
changed. The extension performed no EDA mutation and created no operation or
physical authority.

## Conclusion

The production composition, independent authentication domains, initial
authoritative snapshot, real Host-side EDA observation, and typed candidate
binding were demonstrated. The complete Phase 8.5B user flow was not. The
proposed Phase 8.5B status remains **REAL JLCEDA SMOKE NOT PASS / UNDER REVIEW**.
