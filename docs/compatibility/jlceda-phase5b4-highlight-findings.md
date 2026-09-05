# Phase 5B.4 — Highlight compatibility and evidence limits

## Evidence status

Phase 5B.4b real-runtime smoke-test completion was reported by the user on
2026-09-06. Individual A–E outcomes, provider return values, and visible-effect
observations were not included, so they are recorded as unreported rather than
inferred. Automated Fake-runtime tests and packaging are not observations of
real JLCEDA rendering. Previous Phase 5A
user observations showed successful cross-probe return values without visible
highlight changes; they do not validate this new remote path.

The pinned toolchain remains SDK-compatible packaging 1.6.17, API types 0.4.14,
EDA engine ^3.2.0, Node 24.18.0. Extension release: 0.2.10.

## Reviewed API boundary

Only JlcEdaApiAdapter touches official runtime objects. Remote resolution uses
the statically enumerated read APIs: dmt_SelectControl.getCurrentDocumentInfo,
sch_PrimitiveWire.get/getAll, sch_PrimitiveComponent.get/getAll, and finite
getState_PrimitiveType/getState_Net/getState_Designator accessors. The sole
remote view effect is sch_SelectControl.doCrossProbeSelect. Its component
arguments are resolved designators, not primitive IDs. Components with duplicate
designators across schematic pages are conservatively rejected as ambiguous.

Wire-to-net resolution uses the current primitive's net name. Semantic net
targets are checked against current wire membership. Empty names are rejected;
names are never trimmed/truncated into different identifiers. At most 128
targets are accepted; candidate collections above 4096 cause bounded rejection.
These limits bound our processing, not the provider's internal allocation.

Related official reference pages (read-only API compatibility, not proof of
successful execution):

- https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_primitivewire.get.html
- https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_primitivecomponent.get.html
- https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_selectcontrol.docrossprobeselect.html

Document and selection APIs have BETA compatibility concerns recorded in the
Phase 5A findings; cross-probe itself is documented as public, not BETA. No new guarantee of rendering stability is claimed. The
newer SCH_Net.getNet API is not required or adopted by this slice.

## Safety and semantics

- The real provider supplies no supported fingerprint: strong_required rejects,
  even if a caller supplies an invented fingerprint. Weak identity is explicit.
- Weak checks verify provider, document and resolvable target identity. Snapshot
  equality checks only command coherence; they do not prove content freshness.
  Re-reading the document is not an atomic snapshot or transaction.
- Wire expansion must be explicitly permitted. TTL/style/replace guarantees
  are rejected unless unspecified (null/provider_default/null).
- Provider true means accepted/unverified, false means rejected/unverified,
  invocation exceptions or lost outcome mean indeterminate/unverified.
- Verified target lists stay empty and expires_at stays null.
- Session/generation and a five-second local execution deadline are checked
  again immediately before the provider call. Expired preflight never executes.
- The guarded remote path never clears/restores the selected overlay. The old
  local menu now only explains how to use the guarded script, so it cannot
  bypass scope/guard policy. Legacy adapter regression helpers remain isolated
  from the dispatcher; their old applied/noop labels were corrected.

## Idempotency and uncertain delivery

Python stores one shielded task per key/canonical command; the Extension keeps
one outcome promise per key/canonical command. Object-property order is sorted;
array order remains significant. Session/message IDs are not command identity.
The Extension ledger survives transport reauthentication because its dispatcher
is shared for the loaded extension lifetime. Both ledgers cap at 1024 entries,
reject new keys when full, and never evict records to permit accidental replay.
These are process-lifetime, not durable exactly-once guarantees. Restart is NOT
permission to replay an uncertain command.

Timeout/disconnect/invalid response after sending yields indeterminate and is
not automatically retried. If the reply is unavailable, scope_expansion=none
means no expansion has been confirmed; the warning explicitly records that
absence of expansion is NOT proven. Applications must consult submission_status
and warnings together; a future contract may add an explicit unknown scope.
An unavailable authenticated transport before sending raises not-connected.

Invocation logging is a fixed label without target IDs, tokens or provider
objects. It can support manual counting, not prove visible effects.

## Automated evidence (2026-09-06)

5B.4a Red: missing GuardMode/schema definitions produced Python import/contract
errors and three failing TypeScript contract tests. Green before independent
commit: 119 Python, 14 shared TypeScript contract, 57 TypeScript runtime and
architecture tests. Commit: 28350b9.

5B.4b initial Red: Python 121 tests, five failures and one error; TypeScript
shared contracts had two failures; the dedicated six-test remote-highlight
suite had five failures. Missing message variants and the disabled remote port/
dispatcher were the expected causes. The legacy-label regression additionally
failed three of seventeen tests before correcting accepted/rejected wording.

Final automated totals: 126 Python, 14 shared TypeScript contract, and 70
TypeScript runtime/architecture tests; both strict TypeScript typechecks passed.
They include real local WebSocket tests with a synthetic authenticated peer,
not the JLCEDA host. Build 0.2.10 succeeded; archive contains only extension.json
and dist/index.js (plus the dist directory entry).
The actual-runtime record preserves three independent facts: provider submission
response, program verification status, and human-observed visible effect. The
first and third were not reported in the closeout message. The program remains
UNVERIFIED for JLCEDA because it has no supported visual read-back capability;
human observation must never automatically produce VERIFIED_APPLIED. No Agent,
instrument or design mutation is included.
