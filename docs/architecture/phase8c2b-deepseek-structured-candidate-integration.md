# Phase 8C.2B — DeepSeek One-Shot Structured Candidate Integration

Status: **COMPLETE — architecture review, offline validation, and one bounded real-model safety validation passed**

This ADR defines and records the smallest model-integration boundary that can
replace the Phase 8C.2A scripted candidate producer with one DeepSeek request.
The bounded implementation, offline automated validation, and one separately
authorized real-model safety validation are complete. The authorization was
consumed by that validation and grants no continuing model-call authority. The
phase does not enable inference, diagnosis, hypotheses, next measurements,
EDA, or Hardware execution.

## 1. Decision summary

The accepted direction for implementation review is:

```text
trusted Python Host
  -> Phase 8C.2A PublicationProjection
  -> provider-neutral StructuredCandidateRuntime port
  -> bounded inherited-stdio process adapter
  -> dedicated TypeScript one-shot model executor
  -> frozen LlmRuntime.stream() + frozen DeepSeek adapter
  -> zero Tool schemas and no AgentLoop
  -> bounded raw candidate + raw Egress precheck
  -> private transport receipt
  -> Python teaching-claims/v1 strict parser
  -> Phase 8C.2A deterministic Grounding / Renderer / fallback
  -> independent TypeScript final-Egress one-shot adapter
  -> publish or fail closed
```

DeepSeek is an untrusted selector of request-local aliases. The existing
deterministic publication boundary remains the only engineering authority.

Two different one-shot process adapters are required:

1. a model executor that may perform at most one `LlmRuntime.stream()` call;
2. an Egress-only executor that imports no LLM runtime and applies the existing
   production TypeScript Egress Guard to deterministic final text.

Separating them means a crashed, timed-out, or killed model process cannot make
final Egress unavailable by owning its lifetime. It also avoids porting or
duplicating the TypeScript Egress policy in Python.

## 2. Frozen authority boundaries

The model is not authoritative for evidence truth, values, units, source,
quality, warnings, coherence, comparison status/reason, limitations,
permissions, or sufficiency. Candidate binding values are untrusted echoes.

The model may only select and order aliases from the exact current
`PublicationProjection`. Candidate v1 stays unchanged and contains no factual
prose, numeric value, unit, source field, Tool field, action field, inference,
diagnosis, hypothesis, or proposal.

The following remain frozen and are not duplicated:

- Host-owned projection and alias mapping;
- `permission_content_id` semantics;
- teaching-claims/v1 strict parser;
- `EngineeringClaimGroundingGuard`;
- `GroundedPublicationPlan` and obligations;
- `AIA_CANONICAL_EN_V1` renderer;
- fail-whole candidate handling;
- deterministic fallback;
- final Egress requirement.

## 3. Findings from the frozen Harness source

The reviewed source is the local checkout at commit
`d347e703908d0406b7a7ef80e3a0e594d86b2215`. The relevant packages report
version `0.1.3-alpha.1`.

### 3.1 LlmRuntime API

`LlmRuntime.stream(options)` accepts provider, model, messages, optional system
text, optional Tool schemas, reasoning effort, temperature, maximum tokens,
stop sequences, and `AbortSignal`. It returns `AsyncIterable<StreamChunk>`.

The stream vocabulary contains:

- `block-start`;
- `text-delta`;
- `reasoning-delta`;
- `tool-call-delta`;
- `block-end` carrying a typed content block;
- `usage`;
- one terminal `finish`.

Finish kinds are `stop`, `tool-calls`, `max-tokens`, `aborted`, and `error`.
Adapter selection/iteration failures are normally converted to terminal
`error` or `aborted` finishes. Middleware, consumer, and cleanup exceptions may
still throw and therefore require the executor's outer failure boundary.

### 3.2 Single-attempt behavior

Direct `ctx.llm.stream()` does not run the Harness retry plugin. Retry policy is
consumed by AgentLoop failure handling, which this design does not install.
The DeepSeek adapter normally issues one chat request per direct stream.

The adapter has a special replacement path for stale uploaded image files.
Phase 8C.2B sends text only, mounts no attachment service, and contains no image
blocks, so that path is structurally unreachable. One runtime call therefore
means one application-visible model attempt and one text chat request.

### 3.3 Tools and blocks

`GenerateOptions.tools` is optional. An explicit empty array serializes with no
provider `tools` field. Phase 8C.2B nevertheless watches for
`tool-call-delta`, a `tool-call` block, or `finish.kind == tool-calls`; any such
event rejects the entire response and executes nothing.

Thinking is configured disabled and request reasoning effort is `off`.
Reasoning chunks are still treated as an unexpected non-candidate event and
cause bounded failure, rather than being retained or silently published.

### 3.4 Provider and model configuration

The reviewed DeepSeek adapter registers provider `deepseek-official`. The
existing project real validation selected `deepseek-v4-flash`. Phase 8C.2B
reuses that pair from trusted executor configuration and does not accept either
identifier over stdin or from model output.

Credentials resolve through the existing adapter setting
`apiKeyEnv = DEEPSEEK_API_KEY`; an optional trusted `DEEPSEEK_BASE_URL` remains
the adapter's existing endpoint mechanism. The API key is never a private
transport field.

The adapter also calls `getOrCreateAnonymousUserId()`, which reads or creates
`.anonymous-user-id` under the Harness home. This is model-hidden request
attribution, not model input. Implementation must set `DSH_HOME` from trusted
Host configuration to a dedicated AIA-owned directory; stdin cannot select or
observe it. This means the honest claim is zero model-controlled arbitrary file
access, not zero adapter-internal filesystem activity.

The adapter's default stream-idle timeout is 300 seconds, which is too broad
for this use case. The dedicated executor supplies smaller reviewed bounds and
also uses an outer overall deadline.

## 4. Proposed files

No files in this list are created during the architecture round.

```text
protocols/harness-publication-bridge/v1/
  README.md
  model-invocation-request.schema.json
  model-invocation-receipt.schema.json
  final-egress-request.schema.json
  final-egress-receipt.schema.json
  fixtures/{valid,invalid}/

src/ai_instrument_assistant/application/reasoning/publication/
  model_runtime.py
  model_coordinator.py

src/ai_instrument_assistant/integrations/deepseek/
  structured_candidate_process.py
  final_egress_process.py

src/ai_instrument_assistant/protocol/
  harness_publication_bridge.py

extensions/deepseek-harness/src/model-candidate/
  contract.ts
  prompt.ts
  stream-collector.ts
  one-shot-executor.ts
  runner-boundary.ts
  final-egress-executor.ts

extensions/deepseek-harness/scripts/
  execute-structured-candidate.mjs
  inspect-final-publication.mjs

tests/support/
  scripted_candidate_runtime.py
tests/unit/application/reasoning/publication/
  test_model_coordinator.py
tests/unit/integrations/deepseek/
  test_structured_candidate_process.py
tests/contract/harness_publication_bridge/
tests/architecture/
  test_phase8c2b_model_boundary.py

extensions/deepseek-harness/tests/{contract,unit,architecture}/
  phase8c2b-*.test.ts
```

Fake implementations remain under tests/support and do not enter production
build paths.

## 5. Provider-neutral StructuredCandidateRuntime port

The application port is asynchronous because model generation is remote I/O.
It accepts an immutable bounded `StructuredCandidateRequest` containing:

- Host-generated request ID;
- exact current `PublicationProjection` model projection;
- trusted `TeachingGoal` already represented in that projection;
- fixed prompt-profile identity;
- deadline/cancellation handle supplied by trusted application state.

It returns an immutable `StructuredCandidateOutcome` union:

- `CANDIDATE`: one raw, prechecked, still-untrusted candidate string plus
  bounded transport metadata;
- `FAILED`: stable failure code and bounded metadata, with no raw content;
- `CANCELLED`: stable cancellation category and bounded metadata.

The port exposes no provider name, API key, Tool schema, prompt override,
filesystem path, executable command, authority object, or retry method.
DeepSeek and child-process details belong only to integration adapters.

## 6. Python publication coordinator

The coordinator is the trusted one-attempt owner:

1. evaluate the current envelope and build the Phase 8C.2A projection;
2. create one request ID and invocation projection;
3. call `StructuredCandidateRuntime.generate()` at most once;
4. on `CANDIDATE`, pass the raw string to the existing strict parser and
   deterministic publication boundary;
5. on runtime failure, enter an explicit deterministic fallback entry point;
6. require the TypeScript-backed final `FinalEgressInspector` for normal,
   fallback, and terminal-safe output;
7. produce one outer model/publication audit record;
8. clean up the runtime in `finally`.

Phase 8C.2A currently has no explicit upstream-failure entry point. Feeding it
deliberately malformed JSON to trigger fallback would conflate model transport
failure with parse failure. Implementation should therefore add one narrow
`publish_fallback(reason)` entry that calls the same existing fallback planner,
renderer, and final-Egress path. It must not duplicate or alter fallback
semantics.

The existing Phase 8C.2A audit remains the deterministic-stage record. A new
outer audit wraps it rather than treating its current zero model counters as an
end-to-end count.

## 7. Private Python/TypeScript transport

The transport is inherited stdin/stdout with an exact executable path,
`shell=false`, one request JSON line, one receipt JSON line, and EOF. It is an
application integration transport only. It is not evidence, authorization,
engineering truth, a Tool protocol, or proof of trusted origin.

The child process relationship and inherited pipe handles provide correlation,
not authentication. All receipt fields are still validated and treated as
transport claims. Content digests are identity/check values only.

Model and final-Egress invocations use distinct executables and schemas. The
model executor cannot receive final publication authority. The Egress executor
imports no LLM adapter and cannot make a model request.

## 8. Private schema and versioning

Use a separate namespace:

`protocols/harness-publication-bridge/v1/`

### Model invocation request

Required closed fields:

| Field | Meaning |
| --- | --- |
| `schema_id` | constant request/v1 identity |
| `request_id` | Host-generated UUID |
| `request_digest` | content identity over the complete request |
| `prompt_profile` | constant `AIA_STRUCTURED_CANDIDATE_V1` |
| `projection` | exact bounded output of `PublicationProjection.model_payload()` |

Provider, model, credentials, paths, timeout expansion, Tools, and authority
decisions are not request fields.

### Model invocation receipt

Required closed fields include request ID/digest, status, executor/runtime
version, bounded provider/model IDs, model-request count, raw byte count/digest,
raw-precheck category, terminal finish category, duration bucket, and failure
code. `raw_candidate` is present only when the stream completed normally and
raw Egress was SAFE. It remains untrusted.

Failure receipts never carry raw candidate, provider message, stack, path,
prompt, or secret. Schema conditionals bind legal field combinations for
`CANDIDATE`, `FAILED`, and `CANCELLED`.

### Final-Egress request and receipt

The request contains a UUID, bounded correlation ID, source fixed to
`FINAL_RESPONSE`, and the deterministic rendered text. The receipt contains
only SAFE or UNSAFE plus closed violation categories and correlation. It cannot
alter the text. A missing, malformed, or failed Egress receipt means BLOCKED.

JSON Schema governs individual shapes. One-request lifecycle, process
ownership, deadlines, no-retry behavior, request/receipt correlation, and child
reaping are enforced by code/state tests, not claimed as Schema guarantees.

## 9. Model input projection

Reuse the current `PublicationProjection.model_payload()` exactly. It provides
only:

- projection/context/envelope identities and trusted goal;
- claim limit;
- request-local Alias;
- claim kind/form and subject category;
- source category, metric, availability/quality class when useful;
- exact comparison status/reason category;
- obligation-code hints.

It contains no factual values or units. No provider canonical IDs, internal
evidence references, authorization state, warnings text, artifacts, paths,
waveforms, secrets, or blocked slots cross this boundary.

V1 adds no free-form slot description. The structured selection metadata is
sufficient to distinguish target, instrument, analysis, comparison, and
limitation slots. If descriptions are ever added, they require a separate
reviewed deterministic sanitizer and remain non-authoritative hints.

## 10. Fixed prompt contract

The executor owns one versioned system prompt. It tells the model to:

- return exactly one JSON object conforming to teaching-claims/v1;
- echo the supplied binding fields exactly;
- choose only supplied permission aliases;
- select at least one and at most twelve unique aliases;
- emit no Markdown, prose, explanation, values, units, source claims,
  diagnosis, hypothesis, proposal, Tool call, or extra field.

The user message consists only of fixed instructions, the deterministic model
projection JSON, and a closed candidate skeleton. No caller/model-provided
prompt extension is accepted. Prompt compliance is advisory; security comes
from raw precheck, strict parsing, Grounding, deterministic rendering, and final
Egress.

## 11. TypeScript one-shot executor

The dedicated Cordis context mounts only:

- `LlmRuntime`;
- the exact frozen DeepSeek adapter.

It does not mount AgentLoop, AgentRegistry, ToolRuntime, SessionStore,
SessionProjection, SystemPrompt, Hardware plugin, EDA plugin, attachments, or
filesystem Tools.

The exact GenerateOptions are trusted executor configuration:

- provider `deepseek-official`;
- model `deepseek-v4-flash`;
- one user text message and fixed system prompt;
- `tools: []`;
- thinking disabled and reasoning effort `off`;
- bounded `maxTokens` of 512;
- temperature 0;
- merged AbortSignal for caller cancellation, idle timeout, and total timeout;
- no session ID and no Agent purpose.

The executor calls `ctx.llm.stream()` exactly once or zero times if request
validation/setup fails. Its top-level boundary emits exactly one bounded
receipt and disposes the Cordis fiber in `finally`.

## 12. Strict stream collector

Do not reuse `BlockAssembler` as the security validator: it is intentionally
tolerant of some malformed/partial sequences and defaults an absent finish to
stop. The one-shot executor needs a stricter state machine.

Success requires:

- exactly one text block/index;
- text deltas and final text block agree exactly;
- no reasoning, Tool, image, file, or Tool-result block/event;
- optional bounded usage event only;
- exactly one terminal finish with kind `stop`;
- no chunk after finish;
- iterator reaches completion after finish;
- non-empty output within the byte limit.

`max-tokens`, missing finish, early iterator end, duplicate finish, block
mismatch, unknown block, or thrown consumer/cleanup error is not a completed
candidate. Nothing is incrementally published.

## 13. Tool-event handling and zero-Tool proof

The provider request carries no Tool schema. Even so, any Tool-call chunk or
Tool finish is classified `MODEL_TOOL_EVENT_FORBIDDEN`; the collector aborts
the stream and discards all buffered text.

There is no ToolRuntime or AgentLoop capable of dispatch. The TypeScript module
dependency graph must contain no Hardware/EDA Tool package, and the private
schemas have no Tool/action fields. Tests inject Tool chunks and prove zero
callback, IPC, Hardware, and EDA counts.

## 14. Raw model Egress precheck

After a complete successful text stream, and before writing a candidate receipt,
the executor applies the existing production Egress Guard with a new additive
source classification `MODEL_CANDIDATE_RAW` and the same violation categories.

Byte overflow is enforced during buffering; Egress then checks leakage and
dangerous content. Raw Egress does not parse JSON and does not decide
engineering permission or Grounding. SAFE means only that the raw candidate may
cross the private pipe to Python for strict parsing.

UNSAFE produces `RAW_MODEL_EGRESS_REJECTED`, byte count/digest and category-only
metadata. The raw string is omitted. Existing Phase 7C source classifications
and decisions remain unchanged.

## 15. Strict parser handoff

Python validates the private receipt before reading its candidate field. It
checks request ID/digest, expected executor version, trusted provider/model
configuration, request count, legal status fields, and all size bounds.

Only a valid `CANDIDATE` receipt supplies its raw string to the unchanged
teaching-claims/v1 `StrictCandidateParser`. Exact JSON and Schema failures are
then classified separately from transport or raw-Egress failures. Parsed
candidate bindings remain model claims and are compared to current Host state
by `EngineeringClaimGroundingGuard`.

## 16. Timeouts, cancellation, and buffering limits

Initial implementation bounds:

| Surface | Limit |
| --- | ---: |
| private model request stdin | 96 KiB UTF-8 |
| existing model projection | 64 KiB UTF-8 |
| fixed system prompt | 4 KiB UTF-8 |
| complete model-visible prompt | 72 KiB UTF-8 |
| model candidate | 16 KiB UTF-8 |
| private model receipt stdout | 128 KiB UTF-8 |
| final-Egress request | 20 KiB UTF-8 |
| final-Egress receipt | 8 KiB UTF-8 |
| retained child stderr | 0 bytes; drain/discard after classification |
| stderr diagnostic counter threshold | 4 KiB |
| stream idle timeout | 20 seconds |
| TypeScript total model deadline | 45 seconds |
| Python child deadline | 50 seconds |
| graceful termination/reap window | 2 seconds |
| final-Egress child deadline | 5 seconds |

The Python adapter streams and bounds stdout/stderr instead of calling an
unbounded `communicate()`. It continuously drains stderr to prevent pipe
deadlock but never forwards or stores it; only empty/non-empty/overflow category
is audited.

Cancellation sets the TypeScript AbortController where graceful signalling is
available. Python then closes stdin, requests process termination, waits at most
two seconds, force-kills if necessary, and always reaps. Any result arriving
after cancellation/deadline is discarded.

## 17. Retry policy

There is no retry, repair prompt, fallback model, second stream, Agent retry,
Tool retry, or request replay. A coordinator-local invocation budget is consumed
before the one runtime call and cannot be refunded.

The DeepSeek adapter's registered retry policy is inert because no AgentLoop or
`dsh-llm-retry` executor is installed. Text-only input also excludes the
adapter's stale-image replacement path.

Every failure routes directly to the existing deterministic fallback and final
Egress. Model success is not a safety requirement.

## 18. Bounded failure codes

The model boundary introduces:

- `MODEL_PROVIDER_UNAVAILABLE`;
- `MODEL_REQUEST_TIMEOUT`;
- `MODEL_REQUEST_CANCELLED`;
- `MODEL_STREAM_INCOMPLETE`;
- `MODEL_STREAM_PROTOCOL_INVALID`;
- `MODEL_OUTPUT_TOO_LARGE`;
- `MODEL_TOOL_EVENT_FORBIDDEN`;
- `MODEL_REASONING_EVENT_FORBIDDEN`;
- `RAW_MODEL_EGRESS_REJECTED`;
- `MODEL_OUTPUT_UNPARSEABLE`;
- `MODEL_CANDIDATE_SCHEMA_INVALID`;
- `MODEL_PROCESS_FAILED`;
- `MODEL_RECEIPT_INVALID`;
- `FINAL_EGRESS_PROCESS_FAILED`.

Harness failures such as missing credential, authentication, rate limit,
transport, server, and missing adapter map to bounded application categories;
their raw messages/stacks are never returned. Existing Phase 8C.2A parsing,
Grounding, rendering, Egress, and fallback codes remain unchanged beneath the
outer audit.

## 19. Child-process lifecycle

Python resolves fixed Node and script paths from trusted repository/configured
state and never accepts them from a candidate. It uses no shell. The child
receives an allowlisted environment sufficient for Node, the frozen Harness
root, optional trusted DeepSeek endpoint, and the existing API-key reference.
The API-key value is inherited only for the model child and never serialized.

Lifecycle is:

1. create bounded pipes and child process;
2. write one request line and close stdin;
3. concurrently drain bounded stdout and discarded stderr;
4. validate one receipt line and process exit;
5. in outer `finally`, close handles, terminate if live, wait, kill if needed,
   and reap;
6. discard all late bytes and object references.

The final-Egress child receives no DeepSeek credential and no Harness root. It
loads only the built project Egress module.

## 20. Credential and model selection

The private request contains no credential or credential reference. The model
child uses the existing approved environment/credential seam. No secret is
printed, logged, returned, hashed into audit, or inherited by the Egress child.

`DSH_HOME` is also allowlisted as trusted Host configuration because the frozen
adapter maintains its anonymous attribution ID there. The child receives no
caller-supplied filesystem path and the path is excluded from receipts/audit.

Provider and model are fixed by trusted executor configuration to the reviewed
`deepseek-official / deepseek-v4-flash` route. They are reported back only as
bounded receipt claims and checked against the expected configuration. A later
model change requires compatibility review rather than a stdin override.

## 21. Audit chain

The end-to-end audit is an immutable outer record containing:

```text
trusted goal
-> context fingerprint
-> envelope ID
-> projection ID
-> model request ID/digest
-> expected adapter/runtime version
-> bounded provider/model ID
-> model request count (0 or 1)
-> raw byte count/digest
-> raw precheck category
-> private receipt validation category
-> strict parser category and candidate digest
-> selected aliases after successful parse
-> Phase 8C.2A Grounding result and plan ID
-> renderer version
-> final Egress result
-> published/fallback/blocked status
```

Tool, IPC, EDA, Hardware, and remeasurement counts are always present and zero.
Timing is a coarse bucket, not a precise provider trace. No raw candidate,
prompt, final rejected text, stderr, exception, secret, endpoint, host path, or
provider payload enters the audit.

## 22. Security boundary

- The application core imports only the provider-neutral runtime port.
- DeepSeek imports exist only in the TypeScript integration executor.
- Zero Tool schemas are sent and no Tool/Agent runtime is mounted.
- Candidate v1 cannot express actions or factual prose.
- Model output is never directly published or persisted.
- No authority object crosses the private transport.
- No waveform, artifact body, provider ID, VISA resource, SCPI, EDA object, or
  Hardware result graph is sent.
- Fixed script/module paths and `shell=false` prevent candidate-controlled code
  execution.
- No eval, dynamic method dispatch, arbitrary module name, or source execution
  exists.

This does not claim an OS sandbox around Node. The child necessarily loads the
reviewed Harness modules and inherits narrowly allowlisted process environment.
The security claim is that neither the model nor candidate controls file paths,
modules, Tools, process arguments, or file operations. Strong OS sandboxing is
a later product-hardening topic.

## 23. Fake and scripted tests

The provider-neutral fake runtime supports valid candidate, malformed JSON,
stale binding, unknown Alias, duplicate Alias, Markdown, prefix/suffix prose,
Tool attempt, reasoning event, timeout, provider error, oversized output,
cancellation, invalid receipt, and child cleanup failure.

The TypeScript scripted LLM adapter emits exact `StreamChunk` sequences without
network access. Tests cover normal text, chunk splits across UTF-8 boundaries,
block mismatch, multiple text blocks, reasoning, Tool calls, max-tokens,
aborted/error finish, missing/duplicate finish, late chunks, thrown iterator,
timeout, and disposal failure.

Every failure asserts:

- model request count at most one;
- no retry or repair;
- no raw output publication/logging;
- deterministic fallback or safe BLOCKED result;
- final Egress still required;
- zero Tool, IPC, EDA, Hardware, and remeasurement effects;
- child is reaped.

## 24. Architecture tests

Tests must enforce:

- reasoning core depends only on `StructuredCandidateRuntime`;
- Python process adapters stay under integrations;
- DeepSeek imports stay in the TypeScript model adapter;
- AgentLoop, ToolRuntime, AgentRegistry, SessionStore, Hardware and EDA plugins
  are absent from the executor dependency graph and mount list;
- `tools: []` is explicit and scripted Tool events are rejected;
- exactly one `ctx.llm.stream()` call site exists in the executor;
- no retry loop or retry plugin exists;
- raw candidate has no path to renderer/public result;
- all model failures enter the same deterministic fallback path;
- final Egress uses the existing TypeScript Guard rather than a Python copy;
- process paths and environment are Host-owned and closed;
- every exit path reaps the child;
- frozen protocols have no semantic diff.

Use import graphs, AST/module tests, Schema compilation, process behavior tests,
and controlled fake streams, not ordinary keyword grep as the primary proof.

## 25. Implementation stages after review

1. **Stage 1:** add the provider-neutral async runtime port, fake runtime,
   coordinator, explicit shared fallback entry, and tests.
2. **Stage 2:** add private bridge schemas, shared Python/TypeScript contract
   tests, bounded process adapters, final-Egress process, and fake executor.
3. **Stage 3:** mount the exact frozen `LlmRuntime` with a scripted LLM adapter,
   strict collector, zero Tools, raw Egress, and no AgentLoop.
4. **Stage 4:** run complete offline unit/contract/architecture/integration,
   typecheck, build, security, and frozen-protocol regression.

After Stage 4, stop for Architecture Review. No real DeepSeek call is part of
implementation validation.

## 26. Later real DeepSeek validation

Only a separate explicit authorization may permit one real request. It uses a
recorded/synthetic Phase 8B.3-equivalent context, not real JLCEDA or hardware.
It records one or zero model requests, zero Tools/IPC/EDA/Hardware, bounded
candidate metadata, deterministic Grounding/renderer/fallback, final Egress,
and cleanup.

A valid candidate may publish selected ALLOW claims. Invalid or unsafe model
output may still yield PASS when it is discarded and the deterministic fallback
is safely published. Model obedience is not the safety proof.

## 27. Phase 8C.2B PASS criteria

Phase 8C.2B can be complete only when:

- the private schemas and both language validators agree;
- application request count is never greater than one;
- no Tool or Agent execution surface exists;
- the candidate remains minimal teaching-claims/v1;
- raw output is bounded, prechecked, never directly published, and never
  retained on failure;
- every binding is revalidated against current Host state;
- only current ALLOW evidence/comparison/limitation slots can ground;
- factual text comes only from the deterministic renderer;
- every normal/fallback/terminal publication passes final Egress;
- every failure is bounded and child cleanup is proven;
- complete offline regressions and security audit pass;
- one separately authorized real DeepSeek validation later passes.

Completion does not claim diagnosis, inference, hypotheses, proposals,
autonomous experimentation, EDA access, or Hardware access.

## 28. Protocol impact

Evidence v1, AIA-JLCEDA v1, Hardware canonical schema, Harness-Hardware v1, and
teaching-claims/v1 remain frozen. Only the integration-only
`harness-publication-bridge/v1` namespace is proposed.

The bridge carries invocation and Egress transport data. It is not an evidence
contract or authority protocol, and its hashes do not establish trust.

## 29. Compatibility findings

1. Direct `LlmRuntime.stream()` is the correct fit and remains single-attempt
   without AgentLoop/retry plugins.
2. Empty Tools are natively supported and omitted from the provider wire, while
   Tool-call chunks remain observable and rejectable.
3. `BlockAssembler` is intentionally too tolerant for this strict security
   boundary; a dedicated collector is required.
4. Adapter failures arrive primarily as terminal finish chunks, but outer
   exceptions remain possible and need a runner boundary.
5. The current raw Egress source enum lacks `MODEL_CANDIDATE_RAW`; an additive
   source category is required without changing existing decisions.
6. Phase 8C.2A lacks an explicit upstream-failure fallback entry; a narrow
   additive entry is safer than manufacturing invalid Candidate JSON.
7. The production Egress implementation is TypeScript. A separate Egress-only
   process is required to avoid duplicating it in Python and to keep fallback
   available after model-child failure.
8. The DeepSeek adapter can retry stale image-file representation internally,
   but text-only input makes that path unreachable here.
9. Existing trusted provider/model selection is
   `deepseek-official / deepseek-v4-flash`; no new model is required.
10. The frozen DeepSeek adapter performs one bounded adapter-internal
    read/create of `$DSH_HOME/.anonymous-user-id`; the design must confine that
    trusted path and must not claim total filesystem absence.

## 30. Bounded limitations

- Inherited stdio is local process correlation, not cryptographic
  authentication.
- Invocation/audit state is process-local and not durable recovery state.
- Content digests prove equality only, not authority, freshness, or provenance.
- The model selects relevance/order only; it writes no user-facing explanation.
- The renderer remains constrained English.
- Node is not placed in an OS sandbox by this phase.
- The frozen adapter's trusted anonymous-ID persistence is a bounded filesystem
  side effect; only model/candidate-controlled file access is excluded.
- Application request count cannot prove provider-internal infrastructure did
  not retry outside the observed adapter semantics.
- Provider/model compatibility is bounded to the frozen commit/package and
  reviewed text route.
- Raw Egress is a disclosure precheck, not parser or engineering Grounding.
- No general engineering knowledge source exists.

## 31. Later-phase entry boundary

Phase 8 is complete at this boundary. Proposal-only next-measurement semantics,
reviewed inference rules, hypotheses, causal diagnosis, and iterative workflows
are deferred to separately reviewed Phase 9 work. They inherit no execution or
engineering-truth authority from Phase 8C.2B.

## 32. Review disposition

Phase 8C.2B is **COMPLETE**. The implementation adds the
provider-neutral async port and one-attempt Python coordinator, four strict
private bridge schemas, bounded inherited-stdio adapters, the direct frozen
`LlmRuntime.stream()` executor, dedicated stream collector, raw-candidate
Egress precheck, independent final-Egress child, and the narrow shared
deterministic fallback entry.

Automated tests use fake application runtimes, scripted `StreamChunk` sources,
and local synthetic child processes. They cover complete and malformed streams,
reasoning and Tool rejection, raw Egress rejection, correlation/digest checks,
stdout/stderr bounds, timeout, cancellation, nonzero exit, disposal failure,
and child reaping. Architecture tests establish one `ctx.llm.stream()` call
site, explicit `tools: []`, absence of AgentLoop/ToolRuntime/session/hardware/EDA
composition, and absence of authority fields from the private request.

Final offline results for this implementation review are: 13 focused Python
boundary/contract/process/architecture tests PASS; 12 focused TypeScript
contract/collector/executor/architecture tests PASS; the full Python suite is
525 PASS; the JLCEDA suite is 84 PASS; and the Harness suite is 222 PASS.
Strict TypeScript checks, both production builds, the unified 831-test entry,
Context Pack link verification, frozen-protocol checks, and `git diff --check`
also pass. The initial Red run failed because the port/coordinator, bridge
schemas, and strict collector did not yet exist; no model or external system
was contacted during Red or Green validation.

One separately authorized real request used the reviewed
`deepseek-official / deepseek-v4-flash` route and recorded PASS Case B. The
stream completed with `STOP` and passed raw Egress, but the candidate failed
strict Schema validation with `MODEL_CANDIDATE_SCHEMA_INVALID`. Its content was
discarded, no aliases were accepted, and the existing deterministic fallback,
canonical renderer, and final Egress produced the trusted publication. Tool,
IPC, EDA, Hardware, remeasurement, repair, retry, and second-model counts were
all zero; cleanup and the security audit passed.

The bounded conclusion is **REAL MODEL SAFETY INTEGRATION: PASS** and **REAL
MODEL HAPPY-PATH VALID CANDIDATE: NOT OBSERVED IN THIS VALIDATION**. The result
must not be rewritten as a Schema-valid model candidate. Process and audit
budgets remain process-local; inherited stdio is not authentication; the Node
child is not OS-sandboxed; and the Host must continue to pin and verify the
reviewed Harness checkout before any separately authorized future launch.
