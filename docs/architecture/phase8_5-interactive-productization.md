# Phase 8.5 — Interactive Productization Architecture

Status: **ARCHITECTURE APPROVED; 8.5A COMPLETE; 8.5B.0 CURRENT**
Date: 2026-09-12
Implementation: **8.5A COMPLETE; 8.5B.0 COMPATIBILITY SPIKE ONLY**

This document defines how the completed Phase 8 capabilities become a normal
interactive product without weakening their safety, evidence, or publication
boundaries. The architecture and bounded Phase 8.5A offline foundation are
approved. Phase 8.5B.0 is limited to the separately authorized real JLCEDA UI
and transport compatibility spike. It authorizes no model, instrument, VISA,
measurement, EDA-write, or other external action. Implementation detail and
current limitations are recorded in
[Phase 8.5A Application Host & Runtime Lifecycle](phase8_5a-application-host-runtime.md).

## 1. Decision summary

Phase 8.5 adds adapters and orchestration above the existing modular monolith.
It does not create a second application core in either frontend.

```text
                  DeepSeek Harness Web UI
                   conversation + AIA view
                             |
                  Harness Host-side adapter
                             |
                             v
JLCEDA Extension <----> AIA Application Host <----> existing application core
design companion        authoritative state          evidence / publication
                             |
                             v
                    governed Hardware path
                             |
                         DS1102Z-E
```

The dedicated Python **AIA Application Host** is the root authority. It owns
the interactive session, workflow state, validated UI challenges, runtime
lifecycle, and correlations. Harness remains the primary conversational
surface. JLCEDA remains a design-side companion. Neither frontend owns trusted
decisions, hardware authority, evidence truth, or publication truth.

The proposed delivery sequence is:

| Phase | Scope | Key result |
| --- | --- | --- |
| 8.5A | Application Host and runtime lifecycle | One authoritative workflow state and a bounded frontend command/event boundary |
| 8.5B | JLCEDA interaction surface | Design observation, disambiguation, target/status display, highlight, and safe confirmation surfaces |
| 8.5C | Harness interaction surface | Natural-language goals and evidence-grounded publication through the existing governed core |
| 8.5D | Real interactive validation | One separately authorized, user-facing-only E2E with no CLI actions |

This split is preferred over building each frontend independently because the
Host and its trust boundary must exist before either UI can safely create a
decision.

## 2. Target product workflow

The V1 happy path is:

1. The user starts AI Instrument Assistant, then opens Harness and JLCEDA.
2. The two frontends authenticate to the running local Host through their own
   adapters. Connection does not create workflow authority.
3. The user selects `PWM_OUT` in JLCEDA and asks Harness to inspect or measure
   the current selection.
4. The Host obtains a bounded provider observation through the existing
   read-only JLCEDA adapter.
5. If `Wire — PWM_OUT` and `Component — U1` are both candidates, both
   frontends show that resolution is required. The user chooses the exact wire
   candidate in the JLCEDA AIA surface.
6. The Host validates the candidate identity, observed candidate-set identity,
   design observation, workflow revision, challenge, and expiry. Only then does
   it create the existing trusted design-selection decision.
7. The Host derives and displays a provider-neutral `ProbeTarget`; this is not
   a claim that a probe is physically connected.
8. A measurement request causes the Host to show an exact operation plan. A
   one-shot UI response may cause the Host to issue a workflow-, request-,
   operation-, channel-, and budget-bound `TrustedOperationScope`.
9. For real physical measurement, the Host separately presents the existing
   physical setup fields. All required acknowledgements must be checked. The
   Host validates them against the unchanged plan before creating
   `ProbeSetupConfirmation`.
10. The Host dispatches only through the existing ordered guards and Hardware
    Tool path. The frontend never invokes the driver or transport.
11. Measurement and analysis enter the existing evidence workflow. Publication
    uses the Phase 8 claim policy, structured candidate boundary, deterministic
    renderer/fallback, Grounding, and final Egress.
12. Harness shows the teaching response; both frontends show bounded workflow
    status and evidence summaries. A failed model candidate still produces the
    safe deterministic fallback.

No normal-user step requires a validation script, Python/Node command, JSON
copy, or CLI `A/O/C` token.

## 3. Repository capability findings

### 3.1 Frozen Harness

The reviewed Harness baseline is commit `d347e703...`, package shape
`0.1.3-alpha.1`, and is explicitly a developer preview. The exact reviewed
shape, not later releases, is the compatibility target.

The actual source provides:

- a browser Web UI started by `dsh web`, with loopback Host/Origin checks and
  launch-token to host-only cookie exchange;
- Host-side and browser-side plugin halves declared with `dsh.client`;
- lazily loaded browser bundles and lifecycle-owned plugin disposal;
- a typed slot system with conversation, composer, header, input-dock, details,
  sidebar, and overlay composition points;
- a three-column layout whose details panel can be opened by a plugin;
- session-scoped Remote RPC and Remote Event streams;
- connection generation, baseline-before-events recovery, offline suspension,
  manual reconnect, and bounded jittered reconnect delays;
- structured `ask_user` cards and a transient approval composer with
  **allow once** and **reject**;
- session/conversation messages and cancellation/stop facilities.

The built-in approval seam is useful but insufficient as the AIA physical
confirmation authority. It is valid only during an open Harness turn, carries
a Tool name/call ID/reason rather than AIA target and wiring fields, and its
answerer creates only its own one-shot Harness outcome. It may present a
generic Tool approval after Host validation; it must not mint
`TrustedOperationScope` or `ProbeSetupConfirmation` by itself.

A dedicated AIA Harness plugin can occupy a supported conversation view or
details slot and communicate through a Host-side plugin. It must be composed
and built against the frozen Harness plugin APIs; the repository does not prove
unreviewed future Harness compatibility. The ordinary browser session/cookie
authenticates access to Harness, not authorization for an AIA operation.

### 3.2 JLCEDA extension and SDK

The current extension is a real TypeScript extension using
`pro-api-sdk 1.6.17`, `@jlceda/pro-api-types 0.4.14`, EDA engine `^3.2.0`, and
Node `>=20.17.0` for its build. It already has:

- activation and top-menu entry points;
- bounded document and selection reads through `JlcEdaApiAdapter`;
- guarded semantic highlight submission;
- information, password-input, and toast surfaces;
- authenticated loopback `SYS_WebSocket` transport with bounded reconnect;
- a strict rule that official `eda.*` calls live only in the adapter boundary.

The installed type surface also exposes schematic selection and primitive
events, editor-tab events, confirmation/select dialogs, and
`SYS_Dialog.createDesignPortal()` for a componentized modal/modeless dialog.
The latter is the feasible basis for a richer AIA design companion after a
focused real-runtime compatibility spike.

`SYS_PanelControl` only opens/closes JLCEDA's predefined left/right/bottom
tabs. It does not register a custom dock tab. `DMT_Panel` means a panel-design
document, not extension UI. Consequently V1 must not promise a native docked
custom panel. The reviewed fallback is a menu-opened, modeless componentized
**AIA dialog panel** using the official design-portal component set. If the
runtime spike fails, official confirmation/select dialogs plus the Harness AIA
view are the safe supported alternative. `insertScriptToDialog` remains
forbidden.

Schematic mouse selection events are documented and can trigger a bounded
refresh. Primitive-change and some dialog/select APIs are marked BETA and must
remain capability-detected. Events are hints to re-observe through the adapter;
event payload/order never becomes design evidence. Highlight acceptance still
does not prove visible rendering, as recorded in Phase 5.

## 4. Application Host and bounded contexts

The Python AIA Application Host is a composition root around, not a replacement
for, existing contexts. It owns:

- `ApplicationSession` and `WorkflowSession` repositories;
- workflow revisions and request/event correlation;
- current bounded design observations and trusted selection decisions;
- resolved `ProbeTarget` state;
- pending operation-plan and physical-setup challenges;
- references to issued operation scope and physical confirmation;
- child runtime handles, not driver logic;
- `EngineeringEvidenceContext`, `TeachingDiagnosisContext`, artifact
  references, and publication records;
- sanitized status projections, frontend subscriptions, and audit linkage.

It delegates unchanged business decisions to their existing owners:

| Decision | Existing authority retained |
| --- | --- |
| Provider observation/mapping | JLCEDA Remote Adapter and EDA application services |
| Trusted candidate validation | Design-selection disambiguation service |
| Operation authorization semantics | TrustedOperationScope factory/gate |
| Physical permission | Physical Policy and ProbeSetupConfirmation |
| Instrument behavior | Tool Layer, Instrument Interface, driver, VISA/SCPI |
| Evidence comparison | EngineeringEvidenceWorkflow/comparator |
| Claim eligibility/publication | Phase 8 reasoning/publication pipeline |

The Host is still a modular monolith. Managed child processes provide fault and
resource isolation where already required; they are not independently
authoritative microservices.

## 5. Root lifecycle and startup experience

A dedicated lightweight AIA launcher/Host is the root lifecycle owner. Harness
is unsuitable as the root because it is a developer-preview dependency, may be
closed or reloaded independently, and should not own Python domain state.
JLCEDA cannot be assumed to spawn arbitrary local executables and must not be
given that role.

The V1 Windows experience is one of these equivalent product entry points:

- user starts **AI Instrument Assistant** from a desktop/Start Menu shortcut;
  it starts the Host and offers buttons to open Harness and connection help for
  JLCEDA; or
- an explicitly installed per-user startup task keeps only the lightweight Host
  available, so opening Harness and JLCEDA connects automatically.

The default is the visible launcher, not silent auto-start. A single-instance
guard focuses the existing instance. The launcher shows bounded status and a
Stop action; it never exposes secrets or developer command lines. Harness and
JLCEDA retain their normal launchers and are not forcibly terminated with the
Host.

## 6. Runtime/Lifecycle Manager

The Host-owned manager uses explicit typed runtime handles:

| Runtime | Lifetime | Start condition | Stop condition |
| --- | --- | --- | --- |
| Application Host | persistent/lightweight | product launch | explicit exit or OS shutdown |
| JLCEDA gateway | Host lifetime | Host ready | Host shutdown |
| Interactive frontend gateway | Host lifetime | Host ready | Host shutdown |
| Hardware backend process | on demand | authorized plan approaches execution | idle timeout, completion policy, fatal error, or Host shutdown |
| VISA session | shortest practical | final guarded hardware dispatch | operation completion/timeout or backend shutdown |
| DeepSeek candidate executor | one request/one attempt | evidence and publication envelope ready | stream completion, cancellation, timeout, or failure |
| Final Egress executor | one output | candidate/fallback ready | verdict returned or bounded failure |

Startup and teardown are dependency ordered. Child processes receive explicit
configuration/secret references, readiness deadlines, and a Host generation.
On Windows, the manager uses a job object or equivalent owned-process handle so
children cannot be orphaned. It does not spawn through a shell and never kills
an unknown process merely because a port is occupied.

## 7. Session model

### ApplicationSession

One Host-generation-scoped root session. It owns frontend connections,
workflow index, runtime manager, and status. A Host restart creates a new
generation and invalidates all ephemeral trust.

### WorkflowSession

The sole authoritative user-workflow aggregate. It contains:

- opaque `workflow_id`, monotonic `revision`, and originating request;
- optional Harness conversation binding and current design observation;
- candidate-set identity, trusted design decision, and `ProbeTarget`;
- immutable operation plan identity;
- pending one-time challenges and their expiry;
- issued scope/confirmation references and remaining budget;
- execution delivery state, evidence/publication references, and terminal state.

Only the Host transition service mutates this aggregate, using compare-and-set
against the expected revision. There is no generic workflow scripting engine.

### FrontendConnection

An ephemeral authenticated connection generation for `HARNESS` or `JLCEDA`.
It owns subscriptions and resumable event cursors. It does not own workflow
state, and reconnecting it grants nothing.

A Harness conversation ID may be bound to a workflow for presentation. It is
not the workflow authority. A JLCEDA transport session and a Hardware IPC
session are likewise transport identities, not application sessions.

## 8. Trusted frontend event boundary

Frontend messages are untrusted answers to Host-issued challenges. They never
carry a ready-made domain authorization object.

```text
UI event
  -> authenticate frontend connection
  -> validate interactive schema and size
  -> resolve Host-owned workflow/challenge
  -> verify frontend kind and allowed action
  -> compare workflow revision and expiry
  -> compare exact immutable plan/candidate identities
  -> consume one-time challenge atomically
  -> invoke existing trusted factory/service
  -> commit transition and append audit event
```

Each sensitive challenge binds at least: application generation, workflow ID,
workflow revision, challenge ID, request correlation, action kind, exact
candidate-set or operation-plan identity, allowed frontend kind, issued/expiry
times, and a one-time nonce. Physical confirmation additionally binds target,
channel, maximum expected voltage, ground/wiring statements, and confirmation
scope workflow identity.

The frontend returns only the exact selected candidate or checkbox answers plus
the challenge token. Labels are presentation only. Unknown, missing, expired,
duplicate, replayed, wrong-frontend, or stale responses fail closed without
scope issuance, policy evaluation, IPC, budget use, or hardware side effects.

## 9. JLCEDA interaction surface

The minimum V1 AIA dialog panel has five compact sections:

1. **Connection** — Host, Harness, and Hardware availability/connection state.
2. **Design context** — safe document label, observed candidates, resolution
   status, and observation freshness.
3. **Target/actions** — resolved net/source, Refresh, Resolve Selection, and
   guarded Highlight Target.
4. **Measurement** — operation summary, channel, authorization status, and
   physical confirmation when a Host challenge explicitly allows JLCEDA.
5. **Evidence/Harness** — latest bounded measurement/quality/warnings and an
   `Open in Harness` action if the frozen Harness navigation route is proven;
   otherwise it displays the workflow reference and asks the user to return to
   the already-open Harness conversation.

The extension builds the view only with statically imported, official
component APIs and static event callbacks. It executes no arbitrary script,
HTML, backend-supplied code, raw method name, or EDA mutation. It cannot call
Hardware or model paths. All `eda.*` use remains in `JlcEdaApiAdapter`.

Selection events are debounce/coalescing hints. The adapter performs a fresh
bounded read and the Host creates a new observation. Until the event APIs pass
the 8.5B compatibility spike, manual Refresh remains available. Polling is not
the default.

## 10. Interaction details

### Design selection

The UI lists `Wire — PWM_OUT` and `Component — U1` with non-sensitive type and
label. Hidden binding data holds exact canonical candidate identities and the
candidate-set content identity. `Use selected object` answers the current Host
challenge. The Host, not the extension, creates the trusted selection decision.

Provider primary remains null unless JLCEDA supplies documented primary
evidence. Array order, display name, and visual radio order never choose an
object. If the observation changes, the list is replaced and its old button is
disabled.

### ProbeTarget

After resolution the view says, for example:

```text
Resolved design target: NET PWM_OUT
Source: derived from the selected Wire
Snapshot: observation identity only
Physical probe: not yet confirmed
```

It never implies provider-primary status, physical connection, or immutable
design state.

### Operation authorization

The operation card shows exact semantic operations, target, instrument class,
channel, one-shot invocation budgets, and workflow/request scope. The button is
`Authorize this plan once`, not `Trust always`. The Host re-resolves the plan
and issues the existing scope only after validating the challenge. Any plan
change withdraws the card.

The frozen Harness approval component can display a transient generic approval,
but the AIA Host challenge is still the authority. A custom AIA card is
preferred so exact operation/channel/budget fields are visible. The model never
calls the approval factory.

### Physical confirmation

The card displays target, CH1, 3.3 V maximum expected voltage, and four required
acknowledgements: correct probe target, safe common ground, voltage within the
stated range, and wiring unchanged since the card was opened. `Confirm &
Measure` remains disabled until all fields are checked. Cancellation creates no
confirmation.

The Host compares all answers with the immutable plan, current workflow, target,
channel, and challenge before constructing `ProbeSetupConfirmation`. This is
independent of `TrustedOperationScope` and preserves the Phase 7C workflow
binding repair.

### Provenance and teaching

Default presentation is compact and source-labelled:

| Item | Example source label |
| --- | --- |
| Target | User-provided design expectation |
| Measured | Oscilloscope physical fact |
| Software analysis | Waveform analysis |
| Requirement status | Indeterminate — no explicit tolerance |

An optional details expander may show timestamps, quality, limitations, and
bounded content identities. Content fingerprints are identity only, never
trust/freshness/authentication proof. Raw provider payloads, waveform arrays,
VISA resources, serials, paths, prompts, or rejected model text are absent.

## 11. Controlled workflow state machine

The Host uses this finite state set, with explicit transition rules rather than
free text:

```text
IDLE
 -> OBSERVING_DESIGN
 -> DESIGN_CONTEXT_READY
 -> WAITING_FOR_DESIGN_SELECTION -> TARGET_RESOLVED
 -> OPERATION_PREPARED
 -> WAITING_FOR_OPERATION_AUTHORIZATION
 -> WAITING_FOR_PHYSICAL_CONFIRMATION
 -> READY_TO_EXECUTE
 -> CONNECTING_INSTRUMENT
 -> MEASURING
 -> ANALYZING
 -> BUILDING_EVIDENCE
 -> GENERATING_TEACHING_RESPONSE
 -> COMPLETE

Any non-terminal state -> FAILED | CANCELLED
```

`DESIGN_CONTEXT_READY` may go directly to `TARGET_RESOLVED` only when existing
trusted semantics make resolution unambiguous. Read-only/status operations may
skip physical confirmation only if the existing Physical Policy says it is not
required. No state name itself grants permission. Final authorization and
budget consumption still occur immediately before IPC.

Relevant design, request, target, channel, plan, or workflow changes increment
the workflow revision, withdraw pending challenges, and invalidate dependent
ephemeral scope/confirmation. The Host never silently retargets an authorization.

## 12. Application commands and events

Commands are use-case-specific and typed:

| Command | Caller | Purpose |
| --- | --- | --- |
| `StartInteractiveWorkflow` | Harness adapter | Create a bounded workflow from a supported user goal |
| `ObserveCurrentDesign` | Host/Harness adapter | Request a fresh provider observation |
| `SubmitDesignSelectionAnswer` | permitted frontend | Answer an exact pending candidate challenge |
| `PrepareMeasurementPlan` | Harness adapter | Prepare only currently supported semantic operations |
| `SubmitOperationAuthorizationAnswer` | permitted frontend | Answer an exact one-shot operation challenge |
| `SubmitPhysicalSetupAnswer` | permitted frontend | Answer an exact physical setup challenge |
| `HighlightResolvedTarget` | JLCEDA frontend | Request existing guarded semantic highlight |
| `CancelWorkflow` | either bound frontend | Cancel the current workflow revision |
| `RequestTeachingPublication` | Host orchestration | Publish existing evidence through the Phase 8 pipeline |

`ExecutePreparedMeasurement` is an internal orchestration transition, not a
frontend command. No command accepts SCPI, arbitrary Tool names, arbitrary EDA
methods, domain authorization objects, or model-supplied identity.

Frontends subscribe to safe events such as:

- `ApplicationStatusChanged`, `FrontendConnectionChanged`;
- `WorkflowSnapshot`, `WorkflowStateChanged`;
- `DesignObservationChanged`, `DesignSelectionRequired`;
- `ProbeTargetReady`, `OperationAuthorizationRequired`;
- `PhysicalConfirmationRequired`, `MeasurementProgressChanged`;
- `EvidenceSummaryReady`, `TeachingPublicationReady`;
- `WorkflowCancelled`, `WorkflowFailed`.

Every event has a Host-generated event ID, application generation, workflow
ID/revision where applicable, occurrence time, correlation, type, and bounded
payload. After reconnect, the frontend receives an authoritative current
snapshot before events after its cursor. Event ordering is presentation state,
not engineering evidence or permission.

## 13. Harness interaction architecture

The AIA Harness package gains two reviewed faces in 8.5C:

- a **Host-side adapter plugin** that maps supported conversational intent/tool
  requests to AIA application commands and proxies sanitized snapshots/events;
- a **browser client plugin** that renders an AIA conversation/details view,
  pending decisions, status, cancellation, and evidence summaries through the
  frozen slot system.

The Agent may select only bounded application-intent Tools such as inspect the
current design, prepare an existing measurement, or explain existing evidence.
Selection is intent, not authorization. The Host decides whether a workflow can
be prepared; trusted UI challenges provide user answers; existing final guards
control dispatch.

The existing direct Hardware Tool plugin must not retain its current fail-closed
placeholder as a hidden production authority source. In product composition its
scope/policy context resolvers receive Host-owned context through an explicit
port. The ordered Schema -> scope preflight -> Physical Policy -> final scope
authorization -> IPC pipeline is unchanged.

Conversation output still comes from
`EngineeringEvidenceWorkflow -> TeachingDiagnosisContext ->
AllowedClaimEnvelope -> bounded candidate/fallback -> deterministic renderer ->
final Egress`. There is no UI-only answer generator. Phase 8's real-model
validation remains Case B; no real schema-valid candidate happy path is claimed.

## 14. Local transport and protocol decision

A new, separate **`aia-interactive/v1`** contract is justified because no
existing protocol represents unprivileged frontend commands, Host workflow
snapshots, challenges, and status:

- AIA-JLCEDA v1 is provider observation/guarded view action;
- Harness-Hardware v1 is privileged Tool-to-Hardware IPC;
- Evidence and Hardware canonical schemas are engineering records;
- teaching-claims and publication bridge contracts are publication boundaries.

Overloading any of them would merge authority domains. The new contract has its
own JSON Schema wire source of truth and a separate protocol state machine for
authentication, sessions, correlation, subscriptions, resume cursors,
challenge lifecycle, and version negotiation. Schemas do not define temporal
semantics.

Transport decisions:

- JLCEDA keeps its existing authenticated AIA-JLCEDA connection for provider
  operations and opens a second logical, authenticated interactive connection.
- The Harness browser uses Harness's native Remote RPC/Event channel to its
  Host-side AIA plugin; only that Host-side plugin connects to the AIA Host.
  The browser never receives AIA backend secrets.
- The AIA Host may multiplex the legacy root endpoint and
  `/interactive/v1` on the same user-configured loopback listener if runtime
  compatibility is proven. Protocol authentication/session state remains
  separate even on one TCP port.
- All listeners bind explicit `127.0.0.1`; loopback alone is not authentication.

The new protocol carries presentation projections, challenge answers, commands,
and events only. It carries no raw EDA objects, SCPI, Tool implementation names,
waveform arrays, secrets, or preconstructed trusted domain objects.

## 15. Ports, status, and version compatibility

Current defaults remain owned by their existing processes:

| Endpoint | Owner | Purpose |
| --- | --- | --- |
| `127.0.0.1:49624` | AIA Host/JLCEDA gateway | AIA-JLCEDA v1; proposed path-multiplexed interactive ingress after validation |
| `127.0.0.1:49625` | managed Hardware backend | Harness-Hardware v1, on demand |
| `127.0.0.1:3080` | Harness `dsh web` | Harness Web UI default, independently owned |

No new hard-coded port is proposed. The Host performs a single-instance check
before binding 49624. If the port is held by another process or incompatible
AIA generation, it reports `local_port_in_use`; it never terminates that
process. A user-selected alternate Host port is saved in protected local
settings and entered once through the existing JLCEDA Configure Connection UI;
the Harness Host plugin reads Host-owned local configuration. Longer term, a
per-user named-pipe bootstrap may remove manual port alignment, but it is not a
V1 prerequisite and cannot serve the JLCEDA sandbox directly.

Every connection negotiates protocol name/version and application generation.
Unsupported combinations fail closed with `version_incompatible`. Old sessions,
nonces, challenges, and event cursors are never reused after authentication or
Host generation changes.

The product status projection contains only:

- Host state/version compatibility;
- Harness and JLCEDA connected/disconnected state;
- Hardware `unavailable | available | connecting | connected | faulted`;
- current workflow state/revision and safe display label;
- last stable error code and bounded user message.

It does not expose ports by default, secrets, process IDs, internal paths,
provider payloads, VISA resources, or instrument serials.

## 16. Reconnect, recovery, and cancellation

Frontend reconnect restores safe observations, immutable evidence summaries,
terminal results, and the current workflow snapshot. It does not recreate or
extend trusted selection decisions, pending approvals, scope budget, or
physical confirmation. A pending challenge may be redisplayed only when the
same Host generation, workflow revision, challenge identity, expiry, and
frontend authorization remain valid; otherwise the Host issues a new challenge
after revalidation.

Host restart invalidates all ephemeral authority and in-flight delivery state.
Durable evidence/artifact references may be reloaded only through their existing
integrity/provenance rules. Hardware disconnect marks in-flight delivery using
the existing received/sent-unconfirmed semantics; it never automatically
retries or remeasures. JLCEDA reload creates a new transport session and fresh
observation. Harness reload re-subscribes through a new connection generation.

Cancellation rules:

- waiting for design choice, operation authorization, or physical confirmation:
  atomically consume/withdraw challenges and move to `CANCELLED`, zero IPC;
- before hardware dispatch: scope budget is not consumed;
- after dispatch: cancel local waiting where safe, but do not refund budget,
  replay, retry, or claim the physical operation did not happen;
- VISA calls are only interrupted if the existing driver/transport contract can
  do so safely; otherwise their bounded timeout/cleanup completes;
- model/final-Egress child processes receive cancellation and are terminated by
  the lifecycle manager after a bounded grace period; no replacement attempt is
  made;
- every cancellation invalidates any reusable UI confirmation state.

## 17. Error UX

Machine-readable codes remain stable beneath short teaching-oriented messages:

| Code | User-facing treatment |
| --- | --- |
| `ambiguous_selection` | Explain that the design target must be chosen; show exact candidates |
| `design_observation_stale` | Refresh the selection and ask again; no old decision is used |
| `operation_authorization_required` | Show the exact one-shot plan |
| `physical_confirmation_required` | Explain why wiring/safety must be confirmed |
| `physical_confirmation_stale` | Explain what changed and require a new confirmation |
| `instrument_not_connected` | Keep the plan, show reconnect guidance, do not auto-execute |
| `instrument_disconnected` | Report bounded delivery uncertainty; never auto-remeasure |
| `model_candidate_invalid` | Report that the deterministic explanation was used |
| `fallback_published` | Normal safe-success status, with model limitation available in details |
| `version_incompatible` | Name the incompatible component, not internal protocol payloads |
| `local_port_in_use` | Offer settings/help; never kill the owning process |

No UI receives exception stacks, raw provider errors, absolute paths, raw model
candidates, secrets, VISA identifiers, SCPI, or full serial numbers. A separate
developer mode can retain bounded diagnostics and existing scripts, but is
explicitly enabled and visually separated from product mode. It grants no extra
execution authority.

## 18. Audit continuity

The Host appends bounded correlated records along this chain:

```text
user interaction
 -> frontend connection/event
 -> validated challenge answer/application command
 -> workflow transition
 -> trusted design decision
 -> operation-scope issuance/decision
 -> physical confirmation/policy decision
 -> Tool request and delivery state
 -> Hardware evidence
 -> engineering evidence/context
 -> publication attempt/verdict/fallback
 -> displayed result
```

Records distinguish observation, user answer, Host-created trust object, policy
decision, dispatch, receipt, evidence, and presentation. IDs and SHA-256 values
are correlation/content identities only. They are not authentication,
authorization, trust, freshness, signature, or provenance proof by themselves.
Audit retention never includes secrets, raw waveform arrays, forbidden artifact
URIs, provider payloads, or rejected model prose.

## 19. Security invariants

1. Natural language cannot become raw SCPI, EDA API, or arbitrary Tool dispatch.
2. Tool/model selection is not authorization.
3. UI form validity is not trusted policy evaluation.
4. Only the Host can convert a valid one-time answer into a trusted decision.
5. Operation scope and physical confirmation remain independent and additive.
6. No real physical measurement occurs without the current workflow-bound
   confirmation when Physical Policy requires it.
7. Frontend labels, order, and submitted identities are never identity authority.
8. A reconnect, reload, duplicated event, or replay creates no authority/budget.
9. Final pre-IPC scope authorization remains the only budget consumption point.
10. Frontends cannot call Driver, VISA, SCPI, Hardware IPC, or model processes.
11. JLCEDA remains static-semantic allowlist only; no arbitrary JavaScript,
    HTML, dynamic method dispatch, or design mutation.
12. Evidence, comparison, claim, Grounding, renderer, and Egress logic stays out
    of both frontends.
13. Model text/results cannot create target identity, scope, confirmation,
    evidence, comparison, or diagnosis.
14. All failures remain bounded and produce no automatic Tool/model retry or
    physical remeasurement.
15. Secrets stay in protected Host/process configuration and never in URLs,
    frontend events, logs, or evidence.

## 20. Testing strategy

### 8.5A — Host and lifecycle

- state transition table and illegal-transition property tests;
- one authoritative workflow under concurrent frontend commands;
- CAS/revision conflicts and stale/expired/replayed challenge rejection;
- exact candidate/plan/target/channel/workflow binding;
- Host restart invalidates ephemeral authority;
- reconnect snapshot-before-events and cursor behavior;
- duplicate disconnect/cancellation idempotency;
- managed child readiness, timeout, crash, teardown, and Windows orphan cleanup;
- port collision and incompatible-version fail-closed behavior;
- architecture tests preventing Host/frontend modules from importing Driver or
  communication internals.

### 8.5B — JLCEDA surface

- fake official runtime tests for componentized dialog capability and fallback;
- event coalescing followed by fresh read, listener cleanup on reload;
- ambiguous candidate rendering and exact hidden identity mapping;
- candidate-set and snapshot staleness disables/denies old actions;
- ProbeTarget and observation-only snapshot wording;
- confirmation form completeness and no local trust-object construction;
- sanitized status/evidence display;
- static API allowlist, dependency boundary, and no design mutation/arbitrary
  execution tests;
- manual real JLCEDA UI compatibility smoke test, separately approved.

### 8.5C — Harness surface

- frozen plugin/module/slot compatibility tests;
- natural-language supported goal maps only to a bounded application intent;
- Host pending state blocks Tool IPC;
- model cannot authorize or answer confirmation;
- custom cards preserve exact Host challenge binding;
- cancel/close/reload behavior and session binding;
- safe fallback publication works when the model candidate is invalid;
- no direct browser-to-Hardware or browser secret path;
- full existing Grounding/Egress/Scope/Policy regressions.

### Cross-frontend and security

- JLCEDA selection observation becomes visible in Harness through Host state;
- both views converge on the same workflow revision;
- old UI response cannot authorize a new plan or workflow;
- forged frontend kind, guessed ID, display-name collision, duplicate response,
  reordered event, and stolen cursor all fail closed;
- cancellation before dispatch proves zero IPC and zero side effects;
- receipt tampering and disconnect preserve delivery uncertainty;
- DTO/egress tests prove absence of secrets, paths, serials, raw provider data,
  SCPI, waveform arrays, and rejected model text.

## 21. Staged validation

1. **Fake everything:** Host state machine, both frontend adapters, lifecycle,
   status, cancellation, safety, and publication fallback.
2. **Real JLCEDA + fake Hardware:** separately authorized manual UI validation
   of dialog capability, events, selection/disambiguation, reconnect, and no EDA
   writes.
3. **Recorded/fake EDA + real Hardware:** only if separately authorized; verify
   UI-issued scope/physical confirmation and one-call limits without JLCEDA.
4. **One bounded real interactive E2E:** separately authorize exact target,
   channel, voltage, grounding, operations, budgets, model disclosure, and run.

No architecture or initial UI implementation stage uses DeepSeek, real EDA, or
real hardware.

## 22. Proposed implementation files

The names are proposals for later reviewed phases, not files authorized now:

```text
protocols/interactive/v1/
  README.md
  common/
  commands/
  events/
  fixtures/{valid,invalid}/

src/ai_instrument_assistant/application/interactive/
  models.py
  commands.py
  events.py
  state_machine.py
  challenge_service.py
  host.py

src/ai_instrument_assistant/application/runtime/
  lifecycle.py
  process_port.py

src/ai_instrument_assistant/integrations/interactive/
  gateway.py
  auth.py
  protocol.py
  status_projection.py

src/ai_instrument_assistant/bootstrap/
  application_host.py
  launcher.py

extensions/jlceda/src/interaction/
  aia-dialog-panel.ts
  interactive-client.ts
  view-model.ts

extensions/deepseek-harness/src/interactive/
  host-plugin.ts
  application-client.ts
  commands.ts
  events.ts
  client/                 # frozen Harness browser plugin face

tests/unit/application/interactive/
tests/unit/application/runtime/
tests/contract/interactive/
tests/integration/interactive/
extensions/jlceda/tests/{unit,architecture}/interaction-*.test.ts
extensions/deepseek-harness/tests/{unit,integration,architecture}/interactive-*.test.ts
```

`aia-interactive/v1` should follow contract-first shared Python/TypeScript tests.
Protocol DTOs, frontend view models, and domain/application models remain
separate.

## 23. Phase entry and exit criteria

### Phase 8.5A — Application Host & Runtime Lifecycle

Entry: this architecture is approved; Phase 8 is frozen; existing protocol and
safety regressions are green.
Exit: one tested Host owns application/workflow/frontend sessions, typed
commands/events, challenge conversion, sanitized status, reconnect/cancel, and
managed fake child lifecycles; `aia-interactive/v1` is contract-tested; no real
EDA/Hardware/model is required.

### Phase 8.5B — JLCEDA AIA interaction surface

Entry: 8.5A is committed; a focused runtime spike chooses official design
portal or official dialog fallback without arbitrary scripts.
Exit: the extension shows connection/design/target/workflow/evidence state,
performs exact trusted disambiguation and allowed confirmation answers through
the Host, handles stale/reconnect safely, and retains read-only/static API
boundaries. Automated fake-runtime tests and separately approved real JLCEDA
smoke tests pass; Hardware/model remain fake/off.

### Phase 8.5C — Harness interactive surface

Entry: 8.5A Host contract is stable and the exact frozen Harness client plugin
shape is reconfirmed.
Exit: a user can express supported goals in Harness, see pending AIA cards and
status, cancel, and receive the existing guarded teaching publication. Model
selection cannot create authorization; fake E2E and all Phase 7/8 guards pass.
No Phase 9 reasoning exists.

### Phase 8.5D — real interactive E2E

Entry: 8.5A-C are reviewed/committed; all fake, compatibility, security, and
failure tests pass; exact real actions and disclosures receive fresh user
authorization.
Exit: user-facing actions alone prove:

```text
open product/Harness/JLCEDA
 -> select PWM_OUT
 -> request measurement in Harness
 -> resolve exact selection in UI
 -> authorize exact bounded operation in UI
 -> confirm physical setup in UI
 -> one governed DS1102Z-E workflow
 -> evidence and bounded teaching publication
 -> result in Harness and bounded status in JLCEDA
```

The normal-user action log contains no Python, Node, curl, JSON copy/paste, or
CLI token. Developer logs may observe the run but cannot orchestrate it. Any
real run is separately authorized and preserves exact operation budgets and
delivery semantics.

## 24. Phase 9 boundary and bounded limitations

Phase 8.5 exposes only already-supported inspection, governed measurements, and
evidence explanation. It does not add `NEXT_MEASUREMENT_PROPOSAL`,
`ENGINEERING_INFERENCE`, `HYPOTHESIS`, `CAUSAL_DIAGNOSIS`, autonomous
experimentation, or durable authorization.

Known bounded limitations are:

- the JLCEDA V1 custom **docked** panel is not supported by the reviewed API;
  the feasible surface is a modeless componentized dialog pending a real-runtime
  compatibility spike;
- JLCEDA selection events are observation triggers, not complete evidence, and
  BETA APIs need runtime capability checks;
- guarded highlight acceptance does not prove a visible highlight;
- JLCEDA snapshots remain observation identity only;
- a trusted design choice remains distinct from provider primary and physical
  confirmation;
- `VERIFIED_LINK` does not prove design immutability;
- no tolerance remains `INDETERMINATE / TOLERANCE_UNSPECIFIED`;
- no causal diagnosis is added;
- scope budgeting/authorization is not claimed durable across Host restart;
- Harness is a frozen developer-preview compatibility target;
- Phase 8 real model safety passed through deterministic fallback Case B; a
  schema-valid real-model happy path was not observed;
- model/VISA cancellation may be bounded best effort after an external action
  has started, and never implies rollback;
- one-click startup packaging, signed distribution, installer/updater, and
  production observability require later product hardening after 8.5.

## 25. Protocol preservation

Phase 8.5 proposes no semantic change to Evidence v1, AIA-JLCEDA v1, Hardware
canonical schemas, Harness-Hardware v1, teaching-claims/v1, or
harness-publication-bridge/v1. `aia-interactive/v1` is additive and separated by
authority. The existing historical validation records and Phase 8 limitations
remain unchanged.
