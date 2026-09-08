# Phase 7C.1: Agent Policy Review

Status: **PROPOSED FOR REVIEW — design only** (2026-09-08).

This review defines when a future teaching Agent may expose the five validated
Hardware Tools and how it must describe their evidence. It adds no Agent,
planner, hidden tool call, IPC operation, artifact retrieval, SCPI command, or
Harness-core modification. The current real-hardware result remains **PASS with
bounded runtime observations**; that result does not establish autonomous Agent
safety.

## 1. Tool risk classification

All five operations are observational at the semantic API boundary, but an
observation can still communicate with a physical instrument, depend on a
physical circuit, capture data, or leave execution uncertain after transport
loss. “Read-only” therefore does not mean “zero-risk.”

| Harness tool | Semantic operation | Policy class | Preconditions | Main risk |
| --- | --- | --- | --- | --- |
| `hardware_get_status` | `hardware.get_status` | safe observation | explicit user intent or a visible diagnostic workflow | Contacts the backend/instrument and exposes bounded identity/status metadata. It must not be used as a hidden availability poll. |
| `hardware_measure_frequency` | `hardware.measure_frequency` | physical measurement | valid physical setup confirmation for the requested channel | A wrong probe, channel, voltage domain, or ground can make the evidence invalid or unsafe. |
| `hardware_measure_vpp` | `hardware.measure_vpp` | physical measurement | same confirmation gate | Same physical risk; a plausible number does not prove correct wiring. |
| `hardware_capture_waveform` | `hardware.capture_waveform` | physical measurement plus evidence capture | same confirmation gate and explicit need for waveform evidence | Captures more evidence and creates an opaque, backend-lifetime artifact. It does not authorize sample access. |
| `hardware_measure_pwm` | `hardware.measure_pwm` | physical measurement plus software analysis | same confirmation gate | Combines sequential instrument observations with analysis of one captured artifact; the two evidence sources are not atomic. |

The policy also classifies outcomes independently of the tool:

- **Unavailable/backend-offline:** the call was not delivered, so no
  measurement result exists. The Agent may offer connection guidance but must
  not silently retry.
- **Degraded/partial:** the call returned `ok=true`, but quality, warnings, or
  missing observations limit the evidence.
- **Indeterminate execution:** the request was sent, but no correlated result
  was confirmed. It may or may not have executed; automatic replay is forbidden.

## 2. Physical confirmation policy

Before any of the four measurement tools, the application must hold explicit
user-originated evidence confirming all of the following for this measurement
context:

1. the probe is physically connected to the intended target;
2. the requested oscilloscope channel matches that connection;
3. the signal is known to be safe low voltage for the current setup; and
4. a suitable common ground is present where required.

An EDA selection, net name, `ProbeTarget`, prior measurement, visible waveform,
or model inference is not a substitute for that confirmation. In particular:

```text
EDA selection != ProbeTarget != physical ProbeConnectionConfirmation
```

The LLM must not manufacture or infer `ProbeConnectionConfirmation`. The host
application records it only from an explicit user action. Confirmation is bound
to the intended target, channel, and current setup context; it is invalidated
when the user changes the probe, channel, target, or relevant design snapshot.
If any required fact is absent or ambiguous, the Agent asks for confirmation and
does not call a measurement tool.

`hardware_get_status` does not require a probe confirmation because it does not
measure the circuit. It still requires visible user intent and is not a hidden
background call.

## 3. Tool selection policy

The planner sees only registered semantic capabilities. It cannot request
SCPI, VISA, a Python method, a raw backend method, a dynamic method name, or an
arbitrary IPC operation.

Selection uses the narrowest tool that directly answers the user’s question:

- use `hardware_measure_pwm` for PWM frequency, duty cycle, and amplitude
  together; do not automatically assemble duplicate lower-level measurements;
- use `hardware_measure_frequency` for frequency-only questions;
- use `hardware_measure_vpp` for amplitude-only questions;
- use `hardware_capture_waveform` only when acquisition metadata or a future
  authorized downstream analysis requires a captured artifact;
- use `hardware_get_status` for an explicit connection/identity diagnostic, not
  as a mandatory precursor to every measurement.

One user request should produce the minimum necessary calls. No measurement is
automatically repeated for confidence, transport recovery, a degraded result,
or disagreement between evidence sources. A further call requires an explained
reason and a new user decision where the result is indeterminate or the physical
setup has changed.

## 4. Evidence taxonomy

Every answer must preserve three labels:

- **FACT — instrument observation:** a value reported by the oscilloscope, with
  its source, channel, time/provenance, quality, and warnings where available.
- **ANALYSIS — software-derived result:** a value computed from captured
  evidence, identified with the algorithm provenance and artifact relationship.
- **INFERENCE — interpretation:** a conclusion that compares facts, analysis,
  design expectations, or tolerances. It is not itself a measurement.

Example:

> **FACT:** The oscilloscope reported approximately 10.04 kHz.  
> **ANALYSIS:** The waveform algorithm estimated approximately 10.00 kHz and
> 29.96% high-level duty cycle.  
> **INFERENCE:** These observations appear consistent with a 10 kHz / 30%
> design target, subject to the stated setup and non-atomic acquisition limits.

The Agent must not average instrument and software values, relabel analysis as
instrument evidence, or present an inference as a verified design fact.

## 5. Partial-result policy

`ok=true` means a canonical result was returned; it does not guarantee that all
desired evidence is present or high quality.

When `quality=degraded`, an observation is `unavailable`, or warnings exist, the
Agent must state:

1. which evidence was successfully obtained;
2. which expected evidence is absent or unreliable;
3. the exact bounded warning or quality limitation; and
4. which conclusions remain possible and which do not.

It must not summarize this as “measurement failed.” Conversely, `ok=false`
means the hardware/application operation produced a structured failure rather
than measurement evidence. The Agent reports the bounded error and does not
invent values, reuse a previous result, or imply that missing analysis ran.

## 6. Indeterminate-execution policy

An adapter failure marked `indeterminate_execution` / `SENT_UNCONFIRMED` means
the backend may have started or completed the operation but the client did not
receive a confirmed correlated result.

The required response is:

- say that execution may have occurred;
- say that no result was confirmed;
- do not treat reconnect as permission to replay the call;
- do not reuse the old request/session; and
- ask the user whether they want a new measurement after checking that the
  physical setup remains valid.

The same no-replay rule applies to timeout or cancellation after send. Client
cancellation stops waiting; it does not prove that physical work stopped.

## 7. Artifact policy

A `memory://` `ArtifactReference` is an opaque evidence locator scoped to the
current backend lifetime. The Agent may report its artifact ID, media type,
point count, sample interval, channel, capture time, acquisition mode, and
bounded time/voltage ranges when those fields are present in the canonical
result.

The Agent must not claim to have opened, plotted, inspected, classified, or
recomputed waveform samples. No `artifact.fetch` capability exists in Phase
7C.1, and the URI is neither durable nor a filesystem path. Artifact expiry or
backend restart must not be described as deletion of durable evidence because
durable persistence has not been implemented.

## 8. Teaching response policy

A teaching response should be concise but must explain six things in order:

1. **Decision:** what was measured;
2. **Relevance:** why that measurement addresses the circuit question;
3. **FACT:** what the instrument observed;
4. **ANALYSIS:** what software derived, if anything;
5. **INFERENCE:** what conclusion follows and what design expectation it uses;
6. **Uncertainty:** setup assumptions, warnings, coherence, non-atomic timing,
   missing evidence, or artifact limits.

Raw JSON or a list of numbers alone is not an adequate teaching response. The
Agent should explain units and duty-cycle polarity when relevant, and must not
invent accuracy tolerances. A PASS/FAIL design verdict requires an explicit
acceptance criterion supplied by the design context or user.

## 9. EDA-to-hardware handoff policy

The future supported flow is reviewed as:

```text
DesignSelection + CircuitNet + SignalExpectation   (design evidence)
                    |
                    v
               ProbeTarget                         (candidate)
                    |
          explicit user confirmation
                    v
       ProbeConnectionConfirmation                 (physical evidence)
                    |
                    v
          semantic hardware tool
                    |
                    v
           MeasurementResult                       (observed evidence)
                    |
                    v
           teaching explanation                    (labelled inference)
```

Design and physical evidence retain separate provenance. The Agent may use a
selected `PWM_OUT` net and its 10 kHz / 30% expectation to explain relevance,
but cannot claim the probe is on `PWM_OUT` until the user confirms it. A design
snapshot token is an AIA observation identity, not proof that the board wiring
or live signal matches the design. A stale or changed design/target invalidates
the handoff rather than being silently reconciled.

## 10. DeepSeek Harness integration points

The existing TypeScript plugin remains the only projection of the five static
Hardware Tools into the frozen Harness runtime. Phase 7C should add policy at
reviewed extension points, not modify Harness core or inject planner internals:

- a system/policy prompt describes tool purpose, evidence labels, confirmation
  requirements, and no-replay behavior;
- a configuration layer enables only the five registered semantic tools;
- a deterministic pre-execution policy gate checks application-owned context
  before the plugin sends a measurement request;
- a post-result presenter maps canonical `ok`, quality, warnings, observations,
  coherence, and adapter delivery state into the teaching structure;
- visible UI/application state collects user confirmation and retry decisions.

Prompt guidance is necessary for explanations but is not the security boundary.
The deterministic gate and static allowlist enforce what the model is permitted
to request. Tools must not be invoked during hidden planning, availability
probing, context hydration, or reconnect.

Prompt-level guidance is advisory for model behavior. Deterministic policy
enforcement is authoritative for real tool execution.

## 11. Required Agent context and state

The minimum future policy state is deliberately separate from conversation
memory:

- current registered semantic capabilities and backend availability state;
- the user’s explicit measurement intent and requested quantity;
- selected target/design context, if supplied, with its provider/document and
  snapshot provenance;
- candidate `ProbeTarget`, separate from selection;
- explicit `ProbeConnectionConfirmation`, including target binding, channel,
  confirmer, and timestamp, plus the low-voltage/common-ground attestations
  required by the policy gate;
- proposed operation and validated arguments before send;
- request ID, context ID, connection generation/session correlation, and
  delivery state for the active call;
- canonical result or bounded adapter failure, never an inferred substitute;
- evidence labels, warnings, coherence, artifact opacity/lifetime, and any
  user-provided acceptance criterion;
- whether a retry decision is required after an indeterminate outcome.

Conversation text may explain this state but cannot be its authority. Secrets,
HMAC material, VISA resources, SCPI, raw waveform arrays, local paths, and stack
traces never enter model-visible context.

## 12. Explicitly prohibited unsafe behavior

The future Agent must never:

- infer probe connection, channel, voltage safety, or grounding from EDA data;
- call a measurement tool without the physical confirmation gate;
- generate or request SCPI, VISA, arbitrary JavaScript, raw backend calls,
  dynamic dispatch, or unregistered IPC operations;
- perform hidden hardware calls or background status polling;
- silently retry, replay, or duplicate a sent measurement;
- claim cancellation stopped the instrument operation;
- turn `degraded` into failure or turn `ok=false` into fabricated evidence;
- collapse FACT, ANALYSIS, and INFERENCE into one unsupported assertion;
- inspect or claim access to samples behind an opaque artifact reference;
- expose full serials, secrets, resource strings, paths, stack traces, or raw
  protocol internals;
- claim atomic acquisition, industrial-grade accuracy, durable artifacts,
  future Harness compatibility, or support for unvalidated instruments/modes;
- modify an EDA design or treat highlight/selection as physical verification;
- issue a PASS/FAIL verdict without an explicit acceptance criterion.

## 13. Proposed Phase 7C.2 implementation slice

Phase 7C.2 should remain narrow and test-first:

1. freeze a provider-neutral, immutable Agent policy context containing user
   intent, operation, channel, target reference, confirmation evidence, and
   retry-decision state;
2. implement a deterministic policy decision port returning `allow`,
   `require_confirmation`, `require_user_retry_decision`, or `deny`, with a
   bounded reason—without executing tools;
3. add a Harness-side policy/prompt/config adapter that exposes exactly the
   existing five tools and calls the decision port before IPC; do not modify
   Harness core;
4. add a canonical result-to-teaching-view formatter that preserves FACT,
   ANALYSIS, INFERENCE, warnings, coherence, and opaque artifact semantics;
5. test status intent, all four confirmation gates, changed target/channel,
   degraded/partial results, `ok=false`, offline-before-send, indeterminate
   after-send, explicit retry choice, and prohibition of hidden/replayed calls;
6. use fake policy/tool results for automation first. Real Agent + DS1102Z-E
   execution remains a later, separately confirmed manual HIL phase.

Deferred beyond 7C.2: autonomous planning, artifact retrieval, durable evidence,
new hardware tools, new IPC operations, more SCPI/analysis, Harness upgrades,
and automatic EDA-to-hardware execution.

## Review decision

Phase 7C.1 is ready for architecture review. No production behavior has been
implemented. Proceeding to Phase 7C.2 requires explicit approval of the policy
model, especially the deterministic confirmation gate and no-replay semantics.
