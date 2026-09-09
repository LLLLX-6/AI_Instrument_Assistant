# Phase 7C.4A — Deterministic Agent Egress Guard

Status: **PASS — deterministic Agent egress boundary established**.

## Root cause

Phase 7C.4 proved that the official Harness AgentLoop, real DeepSeek model,
deterministic Hardware Policy, canonical Hardware result, and
TeachingEvidenceContext could all behave correctly while final model-authored
prose remained unsafe. Input minimization and trusted evidence do not prevent a
model from inventing a local path or another sensitive-looking value.

The failure was therefore at the Agent presentation boundary, after trusted
evidence construction but before user-visible reporting. The original Phase
7C.4 report remains `STOPPED — compatibility proposal required`; no lost
measurement values were reconstructed and no real model or hardware was used
during this repair.

## Trust model

All model-generated content is untrusted, including final text, reasoning or
other intermediate text, Tool names and arguments, and model-generated
metadata. Canonical Hardware results, PolicyDecision, and
TeachingEvidenceContext retain their existing trusted/bounded roles, but any
free-text serialization derived from them is inspected before presentation.

The Egress Guard is not an execution authorization mechanism. Tool Schema
validation and the deterministic Hardware Policy remain authoritative for
execution. The guard prevents unsafe model output from becoming visible,
durable, logged, or executable as a Tool call.

The Egress Guard is a disclosure and presentation safety boundary. It does not
prove engineering factual correctness: a response can be egress-safe while
remaining unsupported by evidence. Engineering grounding continues to be
governed by the canonical Hardware result, its deterministic projection into
TeachingEvidenceContext, and the evidence/source semantics carried by that
context. The guard must not become an authority for engineering truth.

## Egress architecture

```text
DeepSeek/provider StreamChunk sequence
        |
        v
Harness llm/stream waterfall (buffered by AIA)
        |
        +--> inspect final/intermediate text
        +--> inspect model-authored Tool arguments
        |
        +--> SAFE: replay original chunks
        |
        `--> UNSAFE:
              discard original chunks
              emit category-only diagnostic
              read trusted per-session PolicyDecision/Evidence snapshot
              render deterministic fallback
              self-inspect fallback
              emit safe replacement text with terminal stop
        |
        v
AgentLoop live assistant-stream events
        |
        v
assistant/message + Tool scheduling + optional persistence
```

The official `llm/stream` waterfall is upstream of AgentLoop chunk publication,
`assistant/message` append, Tool scheduling, and persistence. The integration
buffers the provider response, so an unsafe delta is not exposed before the
complete candidate can be judged. Harness Core is unchanged.

## Violation result model

The immutable result is either `SAFE` or `UNSAFE`. An unsafe result contains
only one or more immutable violations with:

- stable provider-neutral category;
- source: `TOOL_ARGUMENTS`, `FINAL_RESPONSE`, or `INTERMEDIATE_TEXT`;
- bounded request/session correlation id.

It never contains a matched substring, regular-expression capture, original
candidate, Tool arguments, or final response.

Stable categories are:

- `LOCAL_PATH`
- `FULL_INSTRUMENT_SERIAL`
- `VISA_RESOURCE_IDENTIFIER`
- `CREDENTIAL_MATERIAL`
- `RAW_INSTRUMENT_COMMAND`
- `WAVEFORM_SAMPLE_ARRAY`
- `OVERSIZED_OUTPUT`

## Detection strategy

### Local paths

The guard recognizes drive-qualified Windows paths using either separator, UNC
server/share paths, and absolute POSIX paths under common host roots including
`/home`, `/tmp`, `/Users`, `/var`, `/etc`, `/opt`, `/root`, `/workspace`,
`/mnt`, and `/srv`. It does not reject the words “path”, “local path”, or
“Windows paths”. URLs are not classified as local paths by this rule.

### Instrument serials

Known sensitive serial values can be supplied to the pure inspector and are
matched exactly, except canonical masked representations beginning with `***`.
A labelled alphanumeric serial fallback catches invented serial-shaped values
without treating arbitrary long numeric measurement or correlation identifiers
as instrument serials. The Harness integration currently receives only masked
canonical identity, so it has no legitimate raw serial to add to the known-value
set.

### VISA resources

The rule recognizes resource-shaped USB, TCP/IP, GPIB, and serial identifiers
with `::` segments. It does not reject the conceptual word “VISA” or educational
statements that resources are hidden.

### Raw instrument commands

The rule recognizes executable command shapes such as star-prefixed common
commands and colon-delimited instrument command/query trees. The words “SCPI”
and “command” remain valid educational prose.

### Credential material

The guard detects assigned credential environment variables, labelled API
keys/PSKs/HMAC proofs/tokens, bearer-token shapes, common API-key shapes, and
private-key markers. A credential environment-variable name without an assigned
value remains safe, so status statements can say that a value was not logged.

### Waveform arrays

Fields semantically named `samples`, `time_values`, or `voltage_values` are
blocked even when short. Unlabelled numeric arrays are blocked at a bounded
element threshold. Point count, sample interval, and min/max voltage metadata
remain allowed.

### Oversized output

Model final/intermediate text is limited to 16,384 characters and Tool arguments
to 4,096 characters at the Harness boundary. Oversized candidates are discarded;
they are never truncated and treated as safe.

## False-positive policy

Detection is shape-based rather than a keyword blacklist. Tests explicitly allow:

- “SCPI is a command standard.”
- “VISA is not exposed to the Agent.”
- “The waveform artifact is opaque.”
- “The local path is intentionally hidden.”
- bounded waveform acquisition metadata;
- canonical masked serials;
- a credential environment-variable name without a value.

This permits ordinary electronics teaching while blocking executable/resource-
shaped and secret-shaped output.

## Deterministic fallback renderer

The renderer accepts only trusted PolicyDecision, TeachingEvidenceContext,
bounded correlation metadata, and category identifiers. It never calls an LLM,
Tool, IPC client, HardwareToolRuntime, MeasurementService, or Driver.

- Successful measurement: preserves FACT and ANALYSIS items with values, units,
  source, quality, warnings, and limitations; adds no engineering inference.
- Degraded result: preserves available/unavailable evidence and warnings.
- Canonical `ok=false`: reports the bounded failure code and fabricates no value.
- `REQUIRE_CONFIRMATION`: states that no measurement executed and lists missing
  confirmation fields.
- `DENY`: states that policy denied the request and no measurement executed.
- `indeterminate_execution`: states that execution may have occurred, the result
  is unconfirmed, no automatic retry occurred, and explicit remeasurement
  approval is required.
- Egress-only violation without trusted evidence: states that unsafe prose was
  discarded and no measurement or retry occurred.

The completed fallback is itself passed through the same guard. If trusted text
such as a warning still produces a violation, the renderer uses one constant
minimal fallback rather than exposing or truncating that text.

## Retry and side-effect semantics

The interceptor replaces the current provider stream locally. It does not make a
new model request. If unsafe Tool arguments are detected, the replacement stream
contains text only; AgentLoop therefore appends no `tool/call` and schedules no
Tool. If unsafe final prose follows a completed Tool, replacement uses the
already-recorded evidence and makes no additional Tool or IPC call.

Tests assert exact counts:

- unsafe Tool arguments: one model request, zero Tool calls, zero hardware-client
  calls;
- unsafe final response after a measurement: two existing model requests, one
  existing Tool call, one hardware-client call, and no extra request/call;
- unsafe intermediate reasoning: one model request and zero Tool/hardware calls.

No violation path invokes model regeneration, Tool replay, or remeasurement.
Every violation is repaired only by the deterministic fallback renderer; no
model-authored rewrite is accepted as a safety repair.

## Logging semantics

The production diagnostic contains only `status=BLOCKED`, category, source, and
bounded correlation id. The same category-only value is passed to the logger.
Tests prove the diagnostic object is immutable and contains neither the matched
value nor a capture. The original unsafe stream is never handed to AgentLoop and
therefore cannot enter its durable session log.

## Trusted state correlation

A bounded in-memory store relates the latest trusted PolicyDecision and
TeachingEvidenceContext to the Harness session id. The Tool execution records
policy before enforcement and records evidence only after canonical Schema
validation and deterministic projection. Final-response handling reads this
state for fallback and clears it. The store is bounded to 1,024 sessions.

This state is presentation support only. It cannot authorize execution and does
not alter Policy semantics.

## Adversarial and architecture tests

Deterministic fixtures cover invented Windows/UNC/POSIX paths, VISA resources,
raw command shapes, full and masked serials, API keys, PSKs, bearer/private-key
material, sample fields, large arrays, and oversized output. Integration tests
drive the official frozen AgentLoop with scripted malicious output and prove the
unsafe candidate is absent from the durable event log.

Architecture tests enforce that `src/egress` does not depend on Harness, LLM,
IPC, drivers, VISA, SCPI, JLCEDA, generated Hardware contracts,
HardwareToolRuntime, or MeasurementService. The thin Harness interceptor may
depend on the provider-neutral guard and official LLM stream types but cannot
invoke hardware.

## Limitations

- Complete buffering intentionally delays token-by-token display until the model
  response passes inspection.
- Pattern-based detection cannot prove whether an invented value corresponds to
  a real host secret. It treats prohibited shapes conservatively without logging
  them.
- Unlabelled arbitrary alphanumeric serials cannot be distinguished reliably
  from ordinary identifiers without a known-sensitive-value set; the fallback
  catches labelled serial shapes while avoiding broad numeric false positives.
- Provider-internal transient memory is outside this plugin boundary. The guard
  controls what reaches AgentLoop live events, Tool scheduling, project logging,
  validation reports, and durable session persistence.
- Phase 7C.4 remains stopped. Revalidation with a real model and instrument needs
  separate authorization after this repair is reviewed.
