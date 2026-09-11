# Phase 8B.3 — Real EDA and Real Hardware Evidence Workflow

Status: **COMPLETE — architecture reviewed and real validation passed**

This document defines and records the first bounded workflow combining a real
read-only JLCEDA observation with one real DS1102Z-E PWM measurement. Automated
implementation tests used fake/recorded boundaries; the separately authorized
real Attempt 2 later passed. No model, Agent, or EDA write was invoked.

## 1. Goal and non-goals

The target path is:

```text
real JLCEDA document/selection
  -> trusted exact-candidate decision when required
  -> deterministic Wire-to-Net derivation
  -> ProbeTarget
  -> new trusted operation authorization
  -> new trusted physical setup confirmation
  -> governed real hardware invocation
  -> canonical Hardware result
  -> TeachingEvidenceContext
  -> EngineeringEvidenceWorkflow
  -> EngineeringEvidenceContext
  -> TeachingDiagnosisContext
```

Phase 8B.3 proves deterministic evidence association and comparison. It does
not add DeepSeek, AgentLoop, causal diagnosis, autonomous planning, new Hardware
Tools, raw SCPI, EDA mutation, arbitrary JavaScript, automatic retry, or an
invented engineering tolerance.

## 2. Real boundaries and authority owners

The Python validation process is the trusted workflow coordinator. It owns one
fresh `workflow_id`, one fresh `request_correlation_id`, the JLCEDA gateway,
the provider-neutral design projection, the exact candidate decision, the
physical-setup event, the real Hardware backend, evidence assembly, bounded
reporting, and final cleanup.

The existing TypeScript Harness integration remains the authority for semantic
operation scope, Physical Policy, final budget consumption, authenticated
Hardware IPC, canonical-result validation, and `TeachingEvidenceContext`
projection. No Agent or model is loaded.

```text
Python trusted validation coordinator
  |-- localhost :49624 -> JLCEDA Extension (read only)
  |-- in-process real Hardware backend on localhost :49625
  `-- inherited stdio -> one-shot Node governed executor
                           -> existing Harness Tool boundary
                           -> authenticated :49625 IPC
                           -> Python HardwareToolRuntime
                           -> MeasurementService -> DS1102Z-E
```

The two WebSocket services have different ports, protocols, secrets, sessions,
and ownership. They may coexist, but neither can call or authorize the other.

## 3. Implemented architecture and compatibility result

### 3.1 Direct Python hardware invocation is forbidden

`HardwareToolRuntime` and `MeasurementService` do not themselves implement the
Phase 7C `TrustedOperationScope` and Physical Policy gates. A Python validation
runner that invokes them directly would bypass the frozen order:

```text
Schema validation
  -> Operation Scope preflight
  -> Physical Policy
  -> final Scope authorization/budget consumption
  -> IPC
```

Phase 8B.3 therefore does not call the Python runtime directly. The implemented
one-shot Node executor uses the existing `applyWithDependencies` static Tool
path and calls only `hardware_get_status` and `hardware_measure_pwm`. It does
not load DeepSeek or create an AgentLoop.

### 3.2 Private validation-control seam

The Python coordinator and Node executor need one closed, versioned,
validation-only stdio contract. It is carried only over inherited process
pipes, never a listening socket, command-line argument, environment variable,
or persistent authorization file. The request contains bounded workflow,
request, exact probe binding, confirmation, and scope data; it contains no
secret, VISA resource, raw EDA object, JavaScript, or arbitrary operation name.

The response contains bounded dispatch receipts, delivery state, the canonical
masked status summary, the PWM `TeachingEvidenceContext`, measurement channel,
and canonical measurement start/completion times. The teaching context reuses
Evidence v1 rather than redefining it. Both languages validate the same
validation-control schema.

This seam is process-local validation plumbing, not durable production
authorization and not a new public Hardware protocol. If architecture review
does not approve this seam, implementation must stop; duplicating the
TypeScript gates in Python is not an acceptable fallback.

The implemented framing adds two bounded lifecycle messages. Node emits
`backend_start_required` only after the production Tool path has passed schema,
Scope preflight, Physical Policy, and final Scope authorization and is about to
invoke IPC. Python starts its owned backend and replies `backend_ready`. These
messages synchronize lifecycle only; neither one transports an authorization
conclusion.

### 3.3 Existing contract compatibility

No semantic change is proposed for Evidence v1, AIA-JLCEDA v1, the canonical
Hardware Tool schema, HardwareToolRuntime, MeasurementService, or Phase 7C gate
ordering. A small validation-only envelope may reference the existing Evidence
v1 schema. Any implementation that instead requires changing those frozen
semantics must stop for a separate compatibility review.

## 4. Shared workflow identity

At process start the trusted coordinator creates fresh, unguessable values for:

- workflow identity;
- request correlation identity;
- validation-run identity;
- design decision identity;
- operation-scope identities;
- physical-confirmation identity;
- measurement-context identity.

The same workflow and request values must appear in the trusted design
decision, both operation scopes, the physical setup record, both Physical
Policy contexts, the trusted confirmation evidence, and the
`EngineeringEvidenceWorkflowRequest`. Provider payload, Tool arguments,
measurement evidence, model text, and user-entered labels cannot create or
change them.

All authority and invocation-budget state remains process-local. A process
restart invalidates the run and requires new design disambiguation, operation
authorization, and physical confirmation.

## 5. Real JLCEDA lifecycle

1. Verify that the configured endpoint is exactly IPv4 loopback and that the
   coordinator can exclusively own port 49624. Do not attach to an unknown
   pre-existing gateway.
2. Load the existing JLCEDA PSK without displaying its path or value.
3. Start `LocalWebSocketGateway` and wait for exactly one freshly authenticated
   Extension session within a bounded timeout.
4. Read the active schematic and selection once through
   `JLCEDARemoteAdapter`.
5. Project only normalized provider-neutral data. No raw official object is
   retained or reported.
6. If selection is ambiguous, issue a decision only from an exact closed menu
   bound to the current candidate-set fingerprint.
7. Derive at most one Net from an exact Wire and create the design-only
   `ProbeTarget`.
8. Keep the gateway read-only and idle while the physical and hardware stages
   run; stop it in the outermost `finally` block.

The current JLCEDA adapter generates a new `snapshot_id` for each bounded
selection observation. It is not a provider revision and cannot prove equality
across two reads. Phase 8B.3 binds every downstream object to the one accepted
observation; it does not re-read and claim an equal snapshot, and it does not
claim that the EDA design remained atomically frozen during measurement.

## 6. Trusted design decision flow

Provider observation remains unchanged. In particular,
`provider_primary_object` remains null unless JLCEDA supplies documented
primary evidence.

For the expected Wire plus Component observation, the CLI displays bounded
types and labels only:

```text
Multiple design objects observed.
A. Wire — PWM_OUT
B. Component — unavailable
```

The user selects the exact menu key `A`. The Host maps that key to the opaque
identity already present in the current candidate set. Display text and array
position are presentation only and are never identity. The existing resolver
must verify workflow, request, provider, document, snapshot, observation time,
candidate-set fingerprint, and exact candidate membership before the existing
Wire-to-Net derivation runs.

An empty, unsupported, stale, changed, unresolved, or multi-Net result stops
before operation authorization, physical confirmation, Backend startup, IPC,
or hardware access.

## 7. Trusted physical setup record

Design disambiguation and physical confirmation are independent events:

```text
trusted design decision != trusted physical setup confirmation
```

After showing `Resolved design ProbeTarget: PWM_OUT`, the trusted Host presents
a closed confirmation menu. It must enumerate the exact facts being confirmed:

- CH1 is physically connected to the displayed ProbeTarget;
- maximum expected voltage is 3.3 V and the user confirms this as a safe
  low-voltage setup;
- the probe ground is safely connected to circuit GND;
- wiring has been checked and will remain unchanged;
- the confirmation applies only to the current workflow and request.

Only an exact closed action such as `C = Confirm this exact setup` issues the
event; `X = Stop` terminates the run. Free-form yes-like text, model text, EDA
selection, target-name equality, or Tool arguments cannot issue confirmation.

The Host retains one immutable physical-setup record containing the exact
ProbeTarget identifier, design snapshot, canonical target reference, channel,
3.3 V user assertion, safety and ground booleans, unchanged-wiring state,
confirmation source, confirmer, workflow/request scope, and timestamp. It
projects that single event into:

- the existing TypeScript `ProbeSetupConfirmation` and trusted
  `HardwareToolPolicyContext`; and
- the existing Python `TrustedPhysicalConfirmationEvidence` used only for
  cross-reference.

The numerical 3.3 V assertion is retained as bounded Host provenance; the
current Physical Policy consumes the explicit safe-low-voltage confirmation
boolean and does not claim to be a general voltage-threshold calculator.
`wiringChanged=false` is valid only while the Host retains the same setup
record. Any declared or detected wiring change invalidates it immediately.

Before launching the governed executor, the coordinator constructs the record
only from its current trusted identities and validates the private request
schema. The Node boundary independently checks cross-field identity coherence;
Physical Policy remains the authority for the confirmation fields it owns,
and the evidence cross-reference later checks exact probe/snapshot linkage.

## 8. Semantic operation scope and budgets

Operation authorization is a separate closed trusted Host action and cannot be
inferred from physical confirmation. A future real run requires a new explicit
authorization bound to this validation-run identity.

The CLI presents the exact immutable plan before creating either scope:

```text
Authorize this run only:
- read instrument status once;
- measure PWM once on CH1;
- no other Hardware operation and no retry.
O. Authorize this exact operation plan
X. Stop
```

Only the exact closed `O` action issues the two scopes. The later `C` physical
setup action does not enlarge them, and `O` does not assert that the probe is
connected.

Two independent process-local scopes are required because the frozen gate
applies `targetChannel` to every operation:

| Scope | Allowed operation | Channel | Budget |
| --- | --- | --- | --- |
| Status scope | `hardware.get_status` | null | 1 |
| PWM scope | `hardware.measure_pwm` | CH1 | 1 |

Both scopes share the current workflow/request but have distinct scope IDs and
authorization references. The status scope cannot measure. The PWM scope
cannot call status, frequency, Vpp, or waveform capture separately. One PWM
call is the only physical measurement budget.

The Node executor creates one bounded Tool context and resolves one of the two
exact scopes from the statically selected semantic operation. A small optional
diagnostic hook on the existing plugin records actual preflight/final Scope and
Physical Policy decisions without becoming an authority. The same existing
gate performs final budget consumption. Successful authentication cancels no
safety check and does not restore a consumed budget.

## 9. Real Hardware lifecycle and measurement choice

1. Do not open VISA or start the Hardware backend until design resolution,
   operation authorization, physical confirmation, private schema/identity
   validation, Scope preflight, and Physical Policy have succeeded.
2. Construct the existing REAL DS1102Z-E composition only after the trusted
   Host gates. Construction does not connect VISA; the resource remains in
   Python process memory and never crosses to Node or validation output.
3. Start the Node child with a deferred Hardware client. When the production
   Tool path reaches its first governed IPC invocation, Node emits the bounded
   `backend_start_required` synchronization message.
4. Python then connects VISA, starts the authenticated Harness Hardware server
   on exclusive loopback port 49625, and acknowledges `backend_ready`.
5. The Node executor performs one bounded status observation. Failure stops
   before PWM.
6. Keep the bounded one-shot Tool context and authenticated session active.
7. Select the exact PWM scope. Apply Schema validation, PWM Scope
   preflight, Physical Policy, final budget consumption, then IPC.
8. Execute exactly one `hardware.measure_pwm` on CH1.
9. Validate the canonical Hardware result before evidence projection.
10. Project it with the existing `presentHardwareResult` and validate the result
   against Evidence v1 in TypeScript.
11. Dispose Node Tool/IPC state, return the bounded private receipt, stop the
    Hardware server, and close the VISA composition.
12. Validate Evidence v1 again through Python `EvidenceContractBinding`, run
    the evidence workflow using the already-projected evidence, and finally
    stop the JLCEDA gateway.

PWM is the only physical measurement because it already yields instrument
frequency and Vpp, an opaque waveform artifact, software frequency, period,
duty, Vpp, mean, RMS, quality, warnings, and coherence. Separate frequency,
Vpp, or waveform operations would add physical budgets without being required
for this validation.

The status result is a preflight observation, not proof of probe connection and
not the measurement context used for comparison.

## 10. TeachingEvidenceContext mapping

The existing deterministic presenter remains authoritative:

| Canonical Hardware observation | Teaching category |
| --- | --- |
| instrument frequency | `FACT` / instrument -> `PHYSICAL_FACT` |
| instrument Vpp | `FACT` / instrument -> `PHYSICAL_FACT` |
| software frequency and period | `ANALYSIS` / software_analysis -> `SOFTWARE_ANALYSIS` |
| software duty cycle | `ANALYSIS` / software_analysis -> `SOFTWARE_ANALYSIS` |
| software Vpp, mean, RMS | `ANALYSIS` / software_analysis -> `SOFTWARE_ANALYSIS` |
| waveform | opaque `ArtifactReference`; no samples |

Quality and material warnings remain attached to each observation and to the
overall context. Instrument and software values remain separate; they are not
averaged or collapsed.

The validation receipt also preserves canonical measurement channel,
`started_at`, and `completed_at` because the Python cross-reference requires
trusted channel and temporal metadata that is not itself an Evidence v1 fact.
This bounded receipt does not alter Evidence v1.

For private contract v1, `operation.channel` means the channel carried by the
already schema-validated semantic Tool invocation. Therefore status is `null`
and PWM is CH1. Scope/Policy observer events remain argument-free and
observational; receipt accounting must update its initially nullable entry from
the validated invocation arguments at the IPC boundary. It must never derive
channel from operation name, display text, target label, or Hardware result.

## 11. Design target provenance

Unless the real schematic supplies explicit target metadata, the expected
10 kHz frequency and 30% duty cycle are created through the existing trusted
user-target factory:

```text
PWM_OUT structural connectivity -> DESIGN_FACT / JLCEDA-derived
10 kHz and 30% expectations      -> DESIGN_TARGET / USER_PROVIDED
```

The target declaration time and provenance remain explicit. No target is
relabelled as schematic-derived merely because its label matches PWM_OUT.
No tolerance is added to the real validation.

## 12. Cross-reference rule

Comparison can become authoritative only after the existing cross-reference
returns `VERIFIED_LINK`. Before hardware dispatch, the Host must already have
validated the same facts to avoid an unnecessary physical measurement.
After measurement, `establish_evidence_cross_reference` independently requires:

- the exact derived `ProbeTarget`;
- trusted confirmation source;
- matching workflow and request;
- CH1 match;
- exact ProbeTarget identifier;
- exact design snapshot from the accepted observation;
- matching canonical target reference;
- confirmation time not later than measurement start.

Name equality alone never creates a link. If the final cross-reference is not
`VERIFIED_LINK`, the run is NOT PASS and no remeasurement is attempted.

## 13. Temporal and coherence semantics

The runner preserves these separately:

1. active-document observation time;
2. selection observation time;
3. trusted design decision time;
4. ProbeTarget derivation time;
5. operation authorization time;
6. physical confirmation time;
7. Hardware measurement start and completion times;
8. individual instrument/software observation and artifact capture times;
9. EngineeringEvidenceContext assembly time.

Timezone-aware UTC timestamps provide bounded temporal checks. No cross-process
clock precision, simultaneity, atomic EDA and hardware snapshot, or
instantaneous sample identity is claimed. Operation authorization is ordered
by coordinator control flow but does not currently have a separate durable
authorization timestamp.

Required order is selection observation <= decision <= ProbeTarget derivation
<= physical confirmation <= measurement start <= completion <= assembly. The
operation authorization is separately recorded before dispatch and cannot
substitute for physical confirmation.

The PWM result may state `software_observations=same_artifact` and
`instrument_vs_software=sequential_same_session` only when those values appear
in the canonical result. Status and PWM reuse the one fresh authenticated IPC
session in this bounded executor. Instrument and software observations are never described as
simultaneous, atomic, or from one instantaneous sample.

The current in-memory waveform artifact is opaque and backend-lifetime
scoped. Only its already-validated Evidence v1 metadata crosses the boundary;
the Python workflow runs after Backend shutdown and the final record does not
claim durable post-run sample access.

## 14. Comparator behavior

Only `DeterministicEngineeringComparator` is used. Metric matching and unit
conversion remain allowlisted. For real targets of 10 kHz and 30% with no
tolerance:

- frequency may produce separate instrument and software differences;
- duty may produce a software-analysis difference;
- every comparison remains
  `INDETERMINATE / TOLERANCE_UNSPECIFIED`, even when numerically close;
- Vpp, mean, RMS, and period remain evidence without a target comparison.

An automated test may separately use an explicit trusted +/-1% frequency
tolerance and then expect MATCH or MISMATCH. That fixture is not part of the
real validation and cannot add tolerance to the real result.

## 15. Zero-inference and no-model proof

The runner must assert all of the following before PASS:

```text
EngineeringEvidenceContext.inferences == ()
TeachingDiagnosisContext.inferences == ()
TeachingDiagnosisContext.candidate_next_measurements == ()
model_request_count == 0
agent_loop_count == 0
model_retry_count == 0
```

The validation runner and Node executor must have architecture tests proving
that they do not import or call a model provider or AgentLoop. The teaching
projection may contain structured facts, targets, analyses, comparisons,
quality, warnings, coherence, limitations, and unresolved questions only. No
Grounding Guard is invoked because no model candidate exists. Existing
Grounding and Egress behavior remains frozen for a later Phase 8C review.

## 16. Failure and stop behavior

The outer runner owns one bounded failure ledger and never prints exception
messages, stacks, secrets, paths, or raw payloads.

| Condition | Bounded outcome | Dispatch/retry rule |
| --- | --- | --- |
| JLCEDA not authenticated | `EDA_AUTHENTICATION_UNAVAILABLE` | stop; zero Hardware startup |
| ambiguous selection without decision | `DESIGN_DECISION_REQUIRED` | stop; zero confirmation/hardware |
| stale/changed decision | `DESIGN_DECISION_STALE` | stop; no automatic new decision |
| physical confirmation missing/aborted | `PHYSICAL_CONFIRMATION_REQUIRED` | stop; zero Hardware startup |
| confirmation workflow/request mismatch | existing confirmation reason | zero IPC |
| channel mismatch | Scope DENY or policy confirmation mismatch | zero IPC |
| ProbeTarget/snapshot mismatch | `PHYSICAL_TARGET_BINDING_MISMATCH` | stop before Hardware startup |
| Hardware backend unavailable | `BACKEND_UNAVAILABLE` / `NOT_SENT` | stop; no retry |
| instrument unavailable | bounded startup failure or canonical failure | stop; no fallback |
| sent-unconfirmed execution | `INDETERMINATE_EXECUTION` | budget remains consumed; never replay |
| canonical `ok=false` | `HARDWARE_CANONICAL_FAILURE` | zero fabricated facts; no remeasure |
| degraded PWM/waveform | preserve available data and warnings | no automatic remeasure |
| unavailable software frequency | preserve unavailable evidence | no substitution from instrument fact |
| conflicting instrument/software values | retain both sources | no averaging or diagnosis |
| no target | evidence retained; no comparison | no target invented |
| no measurement | bounded missing evidence | no zero/default invented |
| no explicit tolerance | expected indeterminate comparison | not a runtime failure |

If the Node child exits after dispatch may have begun but before a correlated
receipt, the coordinator must conservatively classify the operation as
sent-unconfirmed. It cannot infer NOT_SENT from missing stdout and cannot launch
a replacement worker.

Cleanup is best effort and independent of the primary outcome: disable new
operations, dispose Tool/IPC clients, stop Hardware server, close VISA, stop
JLCEDA gateway, and reap the child process. A cleanup failure after an otherwise
successful child result converts the run to bounded NOT PASS. If a primary
child failure already exists, cleanup failure cannot replace it. Neither case
triggers a retry.

## 17. Automated and real validation plan

### Automated Red-to-Green cases

Fake/recorded tests cover stale design decision, missing confirmation,
confirmation workflow mismatch, channel mismatch, ProbeTarget mismatch,
snapshot mismatch, backend unavailable, instrument unavailable,
sent-unconfirmed delivery, canonical failure, degraded waveform, unavailable
software frequency, conflicting instrument/software values, no target, no
measurement, no-tolerance indeterminate comparison, explicit-test-tolerance
behavior, output sanitization, child failure, and idempotent cleanup.

Architecture tests enforce static operation names, no direct Python runtime
invocation by the runner, no AgentLoop/model dependency, no JLCEDA write API,
no arbitrary dispatch, no raw sample output, and dependency direction. Shared
contract tests validate the private control envelope and reused Evidence v1 in
both Python and TypeScript. Plain keyword grep is not the core architecture
test.

### One primary real scenario

Only after implementation review and a new user authorization:

1. authenticate real JLCEDA and read the active schematic selection;
2. if required, choose the exact Wire candidate from the closed menu;
3. derive Net(PWM_OUT) and its design-only ProbeTarget;
4. obtain a separate exact operation authorization for status once and PWM
   once on CH1;
5. display the target and obtain a new exact physical setup confirmation;
6. start the real backend, perform status once, then PWM once;
7. create and validate real `TeachingEvidenceContext`;
8. run `EngineeringEvidenceWorkflow` with user-provided 10 kHz/30% targets and
   no tolerance;
9. emit a bounded result and cleanly stop every owned boundary.

The complete trusted interaction sequence is therefore `A` (only when the
selection is ambiguous), then `O` (operation authorization), then `C`
(physical setup confirmation). Each is a distinct closed Host event. Selecting
one never implies either of the others.

Negative cases use fake or recorded evidence. Real hardware is not used to
demonstrate denial or failure paths.

### Historical real attempt 1

The first separately authorized real attempt is preserved as NOT PASS in
`docs/validation/phase8b3-real-validation-attempt-1.md`. Real JLCEDA, trusted
selection, operation authorization, physical confirmation, status, and one PWM
measurement executed. The receipt lost the PWM invocation channel after the
Scope/Policy observers initialized accounting without Tool arguments. Python
correctly rejected `channel=null` against expected CH1 as
`hardware / receipt_semantics_invalid`; evidence assembly and model execution
remained blocked. That run's identities and authority are spent.

### Real attempt 2 closeout evidence

After the validation-only channel-provenance repair passed review, the user ran
one separately authorized Attempt 2 through the real runner. The bounded result
was PASS: real design projection was `PROJECTED`; status recorded channel
`null`; PWM recorded channel 1; both operations recorded Scope/Policy ALLOW,
`RESPONSE_RECEIVED`, one IPC dispatch, and one semantic Hardware execution.
Evidence admission produced `VERIFIED_LINK`; all no-tolerance comparisons were
`INDETERMINATE / TOLERANCE_UNSPECIFIED`; inference, next-measurement, and model
counts were zero. Snapshot semantics remained observation identity only.

The bounded record is preserved in
`docs/validation/phase8b3-real-validation-attempt-2.md`. It intentionally does
not reconstruct omitted numeric measurements, quality/warnings, raw identities,
or local configuration. Attempt 1 remains unchanged as historical NOT PASS.

## 18. Security and bounded output

Persistent output contains bounded aliases, types, counts, source categories,
quality, warnings, coherence, comparison states, and masked instrument
identity. It omits:

- full JLCEDA document, primitive, snapshot, candidate, and ProbeTarget IDs;
- raw provider objects or payloads;
- VISA resource and full instrument serial;
- JLCEDA and Hardware PSKs, HMAC proofs, nonces, and session IDs;
- API keys and model content;
- absolute host paths and exception stacks;
- raw waveform arrays and memory artifact URI.

Real identifiers may exist transiently in trusted process memory and the
inherited private pipe when required for exact binding. They are never command
arguments, environment variables, logs, fixtures, or committed validation
documents. Failure records expose stable categories and counts only.

## 19. Backend ownership and cleanup

The coordinator exclusively owns both loopback ports for the validation. It
does not silently attach to unknown pre-existing servers. Port collision,
multiple JLCEDA sessions, missing secrets, or unavailable VISA configuration
fails closed before physical execution.

JLCEDA and Hardware authentication sessions are independent and socket-bound.
The one-shot Tool context uses one fresh Hardware session; no old nonce,
challenge, session, pending request, or budget is reused. At most one Node
executor exists per validation run. The outermost failure boundary guarantees
cleanup after success, user stop, timeout, protocol failure, or assertion
failure.

## 20. Real PASS criteria

PASS requires every item below:

1. real JLCEDA Extension authenticated;
2. real active schematic and selection read once through the read-only adapter;
3. provider observation and null provider-primary semantics preserved;
4. any ambiguity resolved by an exact current-candidate trusted decision;
5. exactly one deterministic Net and design-only ProbeTarget produced;
6. new process-local operation authorization recorded;
7. new physical setup confirmation bound to workflow, request, CH1, exact
   ProbeTarget, snapshot, 3.3 V assertion, safe ground, unchanged wiring, and
   time;
8. status dispatch count exactly one and PWM dispatch count exactly one;
9. physical measurement count exactly one and every other Hardware operation
   count zero;
10. real DS1102Z-E canonical PWM result received and validated;
11. real `TeachingEvidenceContext` created with separate instrument FACT and
    software ANALYSIS evidence, quality, warnings, and coherence;
12. cross-reference state is `VERIFIED_LINK`;
13. `EngineeringEvidenceContext` and `TeachingDiagnosisContext` are created;
14. no-tolerance frequency and duty comparisons are all
    `INDETERMINATE / TOLERANCE_UNSPECIFIED`;
15. inference, diagnosis, and candidate-next-measurement counts are zero;
16. model, AgentLoop, automatic retry, automatic remeasurement, unauthorized
    IPC, EDA write, and raw-sample counts are zero;
17. every owned backend, socket, client, VISA session, and child process is
    stopped or reaped.

Any missing criterion produces NOT PASS. A degraded or failed measurement may
be valuable bounded evidence but does not satisfy the primary real PASS
scenario unless all required observations and linkage facts remain present.

## 21. Stop conditions during implementation

Stop and issue a new Architecture / Compatibility Proposal if implementation
would require:

- duplicating or bypassing Operation Scope or Physical Policy in Python;
- treating a JLCEDA snapshot as a provider revision or comparing independent
  random snapshots as design equality;
- weakening exact ProbeTarget, workflow, request, channel, or temporal binding;
- changing Evidence v1, AIA-JLCEDA v1, canonical Hardware semantics, or Phase
  7C safety ordering;
- inventing timing, simultaneity, coherence, tolerance, diagnosis, or source;
- using model interpretation to decide whether the evidence workflow passed.

## 22. Implemented validation files

The implementation is deliberately outside product Domain and protocol roots:

```text
validation/support/phase8b3/v1/
  request.schema.json
  receipt.schema.json
  fixtures/{valid,invalid}/...

validation/support/phase8b3/
  contracts.py
  coordinator.py
  host.py
  node_executor.py

scripts/
  validate_phase8b3_real_eda_real_hardware.py

extensions/deepseek-harness/scripts/
  execute-phase8b3-governed-hardware.mjs

tests/contract/phase8b3_validation/
  test_contracts.py
tests/unit/validation/
  test_phase8b3_*.py
tests/architecture/
  test_phase8b3_validation_boundaries.py

extensions/deepseek-harness/tests/contract/
  phase8b3-validation-contract.test.ts
extensions/deepseek-harness/tests/unit/
  phase8b3-validation-executor.test.ts
extensions/deepseek-harness/tests/architecture/
  phase8b3-validation-boundary.test.ts
```

The validation schema is a private, versioned process contract and reuses the
existing Evidence v1 teaching-context schema. No new production Domain model,
Hardware Tool, JLCEDA operation, Agent capability, or persistent service was
introduced.

Automated tests establish: the ambiguous Wire path resolves to exactly one Net;
the operation-authorization and physical-confirmation actions remain
independent; pre-hardware failures cause zero backend start/IPC; actual Scope
and Physical Policy decisions are captured; SENT_UNCONFIRMED is not replayed;
backend and child failures clean up; Evidence v1 is parsed again in Python;
no-tolerance comparisons remain indeterminate; and final contexts contain zero
inference or next-measurement proposal.

The private receipt is transport evidence about execution accounting, not a new
engineering fact source. Its canonical Hardware result is projected through the
existing presenter; only Evidence v1 enters `EngineeringEvidenceWorkflow`.
Public validation output replaces the private receipt with a bounded summary
and omits provider native IDs, VISA resource, secrets, full serial, artifact
URI, sample arrays, exception details, and absolute paths.

### 22.1 Frozen snapshot limitation

`snapshot_id` remains an AIA observation identity. A verified cross-reference
means the measurement is associated with the exact ProbeTarget derived from
that accepted observation in the governed workflow. It never means JLCEDA
proved the document unchanged between observation and measurement. The bounded
result carries this limitation explicitly.

### 22.2 Real-validation closeout

Attempt 1 is historical NOT PASS and Attempt 2 is bounded PASS. Neither record
authorizes another run. Phase 8B.3 is COMPLETE following closeout Architecture
Review. Any future real execution would require a new review as applicable,
fresh run-scoped operation authorization, fresh physical confirmation, and new
trusted identities.

## 23. Phase 8C entry criteria

Phase 8B.3 satisfied its entry conditions for Phase 8C: implementation and
closeout were reviewed, the fresh real scenario passed, historical failures
remain preserved, and the combined evidence path produced zero inference and
diagnosis with clean shutdown. Phase 8C is CURRENT, but implementation has not
started.

Entering Phase 8C still requires a separate architecture review for causal
inference vocabulary, evidence sufficiency, uncertainty, model input/output,
Grounding/Egress treatment, next-measurement proposal versus authorization,
and renewed real-operation authority. Phase 8B.3 completion alone cannot
authorize an Agent, diagnosis, planning, or additional measurement.
