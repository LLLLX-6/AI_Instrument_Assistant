# DeepSeek Harness Phase 7A Compatibility Review

Status: review complete; Phase 7B is not authorized or implemented.

Review date: 2026-09-06 (Asia/Shanghai).

## Evidence labels

Every material statement in this review uses one of these labels:

- **OFFICIAL FACT** — stated by the DeepSeek Harness repository, its current
  documentation, or the official DeepSeek API documentation.
- **PROJECT FACT** — observed in the current AI Instrument Assistant repository.
- **INFERENCE / RECOMMENDATION** — a design conclusion drawn from the two
  contracts. It is not represented as a DeepSeek guarantee.

## 1. Reviewed baseline

**OFFICIAL FACT:** The reviewed upstream branch head was commit
[`d347e703908d0406b7a7ef80e3a0e594d86b2215`](https://github.com/deepseek-ai/deepseek-harness/commit/d347e703908d0406b7a7ef80e3a0e594d86b2215),
dated 2026-09-04 and labelled `dsh@0.1.3-alpha.1`. The review used files pinned
to that commit wherever possible:

- [README](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/README.md)
- [Development guide](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/development.md)
- [Architecture](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/architecture.md)
- [Tool authoring cookbook](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/cookbook/adding-a-tool.md)
- [Tools subsystem](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/subsystems/tools.md)
- [Plugin lifecycle](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/user/develop/framework/index.md)
- [Services and dependencies](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/user/develop/framework/service.md)
- [Plugin configuration](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/user/develop/basic/config.md)
- [Plugin packaging](https://github.com/deepseek-ai/deepseek-harness/blob/d347e703908d0406b7a7ef80e3a0e594d86b2215/docs/user/develop/basic/publish.md)

**OFFICIAL FACT:** The repository requires Node.js `^22.19.0 || >=24.0.0`
and pins pnpm 11.7.0 for source development. Harness is explicitly a developer
preview and its README warns that compatibility-breaking changes will occur.

**PROJECT FACT:** Local discovery on the review date found:

- Node.js 24.18.0, npm 11.16.0 and Python 3.12.14;
- npm registry versions `@deepseek-ai/dsh@0.1.2-rc.1`,
  `@deepseek-ai/dsh-tools@0.0.1-rc.1` and `@deepseek-ai/cordis@4.0.2`;
- no DeepSeek Harness package in the project manifests or lockfiles;
- the Phase 6G baseline at commit `ce6440c`.

**INFERENCE / RECOMMENDATION:** The machine satisfies the Node and Python
floors, but the reviewed master documentation and registry release set are not
the same version. Phase 7B must pin and test one coherent published package set.
It must not compile against moving `master` while installing older registry
packages.

## 2. Official plugin and service model

**OFFICIAL FACT:** Harness is built on Cordis. A plugin is a TypeScript module
that exports an `apply(ctx)` function. It declares required services with
`inject`; a tool plugin declares `inject = ['tools']`. Cordis runs `apply` only
after required services exist. If a required service disappears, dependent
plugins are disposed and loaded again when it returns.

**OFFICIAL FACT:** Capabilities use Service Definition, Service Provider and
Consumer roles. The tool registry is the `ctx.tools` service. Adding a
model-facing capability is done beside the agent loop by registering with this
service, not by modifying the loop.

**INFERENCE / RECOMMENDATION:** The electronics integration is a Consumer of
`ctx.tools` and a client of the Python electronics backend. It must not become a
second implementation of MeasurementService, the Rigol driver or analysis.

## 3. Official Tool registration contract

**OFFICIAL FACT:** The current documented registration form is:

```text
ctx.tools.register(defineTool({ ... }))
```

`defineTool` binds:

- model-facing `name`, `description` and `parameters`;
- mandatory canonical `output.schema`;
- pure `output.render(args, value)`;
- asynchronous `execute(args, exec)` returning the canonical lossless JSON
  value;
- optional presentation/finalization callbacks;
- optional `timeoutMs` and `isConcurrencySafe` execution metadata.

Arguments are validated and frozen before the tool body. A successful body
value is checked against its output schema before rendering.

**PROJECT FACT:** `HardwareToolRuntime.execute(payload)` is synchronous and
already validates the complete request and returned runtime envelope using the
project-owned Hardware Tool Contract.

**INFERENCE / RECOMMENDATION:** The Harness plugin must implement asynchronous
I/O and call the Python runtime through an IPC client. It must not reproduce the
runtime handler logic in TypeScript.

## 4. Official Tool schema capabilities

**OFFICIAL FACT:** The enforced raw-schema vocabulary currently supports:

- one scalar `type` per node: object, array, string, number, integer, boolean or
  null;
- recursive `properties`, `required`, boolean `additionalProperties` and
  `items`;
- `oneOf` with at least two branches and exact-one-match semantics;
- scalar `enum` and `const`;
- non-validating description, title, default and examples annotations.

Unsupported or malformed keywords are rejected rather than ignored. The
`defineTool` parameter DSL uses the same constrained vocabulary. Its implicit
parameter root is open unless a raw closed object schema is used.

Therefore:

| Required shape | Harness capability |
|---|---|
| Nested objects | Supported |
| Arrays | Supported |
| Optional property | Supported by omitting it from `required` |
| Nullable value | Supported as `oneOf` with a `null` branch |
| Discriminated union | Expressible with `oneOf` plus branch `const` values |
| `$ref`, `$defs`, `allOf` | Not in the enforced subset |
| `format`, lengths, numeric bounds, `uniqueItems` | Not in the enforced subset |
| Streaming tool result | No streaming return type in `ToolDefinition.execute` |

**PROJECT FACT:** `protocols/hardware/v1/hardware-tool.schema.json` is Draft
2020-12 and uses `$id`, `$defs`, `$ref`, `allOf`, type arrays, `format`, string
lengths, numeric bounds and `uniqueItems` in addition to the common subset.

**INFERENCE / RECOMMENDATION:** The canonical project schema cannot be passed
directly to `ctx.tools.register`. Phase 7B needs a deterministic, tested Schema
Projection that dereferences the canonical schema and emits the narrower
Harness vocabulary for each tool. Full validation remains mandatory in Python
before and after execution. A second hand-maintained DTO schema is rejected.

## 5. Output, error, timeout and cancellation semantics

**OFFICIAL FACT:** A successful Harness tool execution has `isError: false`, a
validated canonical JSON `value` and rendered `content`. A failed execution has
`isError: true`, a `ToolFailure`, no successful value, and rendered error
content. Invalid arguments, invalid output, policy denial and thrown tool errors
are normalized through this failure path. The canonical successful value is
execution-local; durable session events retain rendered content, error and
metadata.

**OFFICIAL FACT:** `execute` receives an `AbortSignal`. Async work must observe
or forward it and settle only after its owned work becomes quiescent. Declaring
`timeoutMs` asserts that this cooperative behavior exists; the separate timeout
policy plugin enforces the budget. Harness cannot hard-kill same-process code.

**OFFICIAL FACT:** `presentCall` may describe a pending UI state while the model
response is streaming, but the tool body itself returns one Promise containing
one canonical result. No incremental tool-output stream is part of the current
`ToolDefinition` contract.

**PROJECT FACT:** HardwareToolRuntime returns a validated JSON envelope for
expected hardware outcomes, including `ok=false` and stable error codes. It
catches provider exceptions and does not expose raw exception text. It does not
currently accept an external cancellation signal. The underlying VISA path has
bounded I/O timeouts, but that is not equivalent to cooperative Harness
cancellation.

**INFERENCE / RECOMMENDATION:** Use two non-overlapping error layers:

1. Expected hardware/domain outcomes remain successful Harness canonical
   values containing the full `ok=true` or `ok=false` Hardware Tool envelope.
2. IPC corruption, authentication failure, unavailable backend, schema drift or
   plugin defects become Harness execution failures with bounded adapter-level
   messages.

This preserves project error details and avoids a duplicate representation of
the same failure. `timeoutMs` must initially be omitted. A request cancelled or
timed out at the Harness side must not settle until the backend confirms that
the associated hardware workflow completed, was safely cancelled, or otherwise
reached quiescence.

## 6. Partial-result compatibility

**OFFICIAL FACT:** Harness only requires a successful tool value to satisfy the
declared output schema. It does not require application-level quality to mean
Harness success or failure.

**PROJECT FACT:** A completed measurement may be `quality=degraded` with
warnings and partial observations while remaining a valid result. Provenance
and coherence describe how that evidence was produced.

**INFERENCE / RECOMMENDATION:** `quality=degraded` is a Harness execution
success. It must remain `ok=true` with warnings and available observations.
Only an invalid or unavailable execution boundary is a Harness failure.

## 7. Concurrency model

**OFFICIAL FACT:** A Harness tool participates in sibling concurrency only when
`isConcurrencySafe(args)` returns exactly `true`. Omission, errors, invalid
arguments and every other return value fail closed to exclusive execution.

**PROJECT FACT:** HardwareToolRuntime owns a process-local workflow lock around
each complete operation. Real measurements share one stateful oscilloscope.

**INFERENCE / RECOMMENDATION:** Omit `isConcurrencySafe` for all five hardware
tools. Keep the Python workflow lock as the final serialization boundary even
if future Harness configuration changes scheduling. Do not add transparent
retries: repeated acquisition is a new physical observation and creates a new
artifact identity.

## 8. Tool naming compatibility

**OFFICIAL FACT:** Harness' provider-neutral `ToolSchema` documents `name` as a
string and requires uniqueness in a registration scope. The DeepSeek Responses
API additionally requires function names to match `^[a-zA-Z0-9_-]+$`, be
non-empty and no longer than 128 characters. Dots are not allowed by the actual
DeepSeek provider wire contract.

Source: [DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/).

**PROJECT FACT:** The canonical operations use dotted names and are already
part of the frozen Hardware Tool Contract.

**INFERENCE / RECOMMENDATION:** Register five independent Harness tools using
adapter aliases. Do not rename the Python operations:

| Harness tool name | Canonical Python operation |
|---|---|
| `hardware_get_status` | `hardware.get_status` |
| `hardware_measure_frequency` | `hardware.measure_frequency` |
| `hardware_measure_vpp` | `hardware.measure_vpp` |
| `hardware_capture_waveform` | `hardware.capture_waveform` |
| `hardware_measure_pwm` | `hardware.measure_pwm` |

The mapping is static, one-to-one and exhaustively tested. No generic
`execute_hardware(operation, args)`, `raw_tool`, `send_command` or dynamic
method dispatch is permitted.

## 9. Plugin configuration

**OFFICIAL FACT:** A configurable plugin exports a TypeScript `Config` type and
a same-named Schemastery schema. Cordis validates configuration and fills
defaults during load. Invalid configuration fails plugin loading. Configuration
is supplied by the plugin's `cordis.yml` row and may trigger hot replacement.

**INFERENCE / RECOMMENDATION:** Model-invisible plugin configuration should be
limited to the backend endpoint, credential reference, connection/request
budgets, rendering policy and development diagnostics. It must not accept SCPI,
VISA resource names, arbitrary executable arguments, operation names or source
code from model tool arguments. Secrets should be resolved from protected local
storage or an injected credential service, not embedded in `cordis.yml`.

## 10. Plugin lifecycle mapping

**OFFICIAL FACT:** Cordis defines this Fiber lifecycle:

```text
PENDING -> LOADING -> ACTIVE
                   -> FAILED
ACTIVE  -> UNLOADING -> DISPOSED
```

`PENDING` means required services are absent. `LOADING` runs `apply`.
`ACTIVE` means the plugin is mounted. Registrations through `ctx`, including
tools, are automatically undone on unload. Custom network resources belong in
one `ctx.effect()` disposer. Multiple disposers may run concurrently, so
order-dependent shutdown steps must be kept in one async disposer.

**INFERENCE / RECOMMENDATION:** The IPC connection has its own lifecycle and
must not be confused with the Cordis Fiber state. The plugin should be ACTIVE
when its configuration is valid and the `tools` service is present, even while
the backend is temporarily offline. Otherwise a transient backend outage would
turn into `FAILED` during `apply` and defeat controlled reconnect.

Recommended mapping:

| Cordis state | Hardware adapter responsibility |
|---|---|
| PENDING | Wait only for declared Harness services such as `tools` |
| LOADING | Validate config, construct client, register owned effect and tools |
| ACTIVE | Maintain authenticated connection and bounded reconnect state |
| FAILED | Reserve for invalid config or unrecoverable plugin construction |
| UNLOADING | Stop new sends; quiesce calls; close connection; clear secrets/session |
| DISPOSED | No tools, sockets, timers or pending Promises remain |

Development should connect to an explicitly started backend for easy diagnosis.
Production Windows desktop should supervise the Python backend independently
and let the plugin connect to it. Tests should replace the IPC client with a
deterministic fake rather than start VISA hardware.

## 11. Packaging and installation

**OFFICIAL FACT:** A local scratch plugin can be mounted with a `--patch`
overlay. An installable plugin is an npm bundle whose `package.json` declares
`dsh.bundle.patch`; the patch contributes Cordis rows. A profile lives under
`$DSH_HOME/profiles/<name>`, lists ordered bundles and is run using
`dsh --profile <name>`. `dsh plugin --profile <name> add ...` installs and
activates a bundle.

**OFFICIAL FACT:** Git-host installation receives source, so a TypeScript
package needs an allowed `prepare` build. pnpm treats that allowance as install-
time code execution outside the agent sandbox. Official guidance recommends a
pinned commit and offers prebuilt npm packages or tarballs to avoid this build
permission.

**INFERENCE / RECOMMENDATION:** Use this sequence:

1. Monorepo `extensions/deepseek-harness` development adapter mounted by a
   development patch.
2. Contract and fake-backend validation against exact Harness dependencies.
3. Prebuilt local tarball for manual integration testing.
4. Separate npm bundle only after the preview API and packaging are proven.

The Python Electronics Backend remains separately packaged and supervised. The
npm bundle must not silently download Python, drivers or VISA components during
installation.

## 12. Python to TypeScript boundary options

### Option A — plugin-spawned Python subprocess

| Concern | Assessment |
|---|---|
| Startup/shutdown | Simple ownership; one Cordis effect can spawn and terminate it |
| Crash recovery | Plugin must supervise process and must not retry an in-flight measurement |
| Correlation | Requires its own request IDs and late-response handling |
| Timeout/cancellation | Process ownership helps hard-stop, but hard-kill may leave the instrument in unknown state |
| Concurrency | Python lock still required |
| Schema/error mapping | Same adapter projection and runtime validation required |
| stdout/stderr | High framing risk: stdout must contain protocol frames only; diagnostics must use stderr |
| Authentication | No network peer authentication, but executable/path/config become trust boundaries |
| Local attack surface | Smaller network surface; larger process-launch/configuration surface |
| Windows | Requires hidden-window/process-tree and shutdown handling |
| Artifact lifetime | Ends when the plugin/subprocess reloads or crashes |
| Testability | Strong; a fake worker is straightforward |
| Packaging | Plugin must locate a compatible Python environment and installed project |

**INFERENCE / RECOMMENDATION:** Option A is useful for tests and an early
developer proof, but not preferred for production. Harness HMR would otherwise
restart the Python owner and invalidate in-memory waveform artifacts.

### Option B — authenticated localhost IPC to persistent Python backend

| Concern | Assessment |
|---|---|
| Startup/shutdown | Backend lifecycle is independent; plugin only connects/disconnects |
| Crash recovery | Bounded reconnect can recover without replacing electronics state |
| Correlation | Requires message ID, reply ID, session and operation agreement |
| Timeout/cancellation | Requires server-side operation tracking so reconnect never duplicates a physical capture |
| Concurrency | Backend lock remains authoritative |
| Schema/error mapping | Existing Hardware Tool validator remains at the Python boundary |
| stdout/stderr | Protocol framing is independent of process console output |
| Authentication | Requires challenge-response, fresh nonces, session binding and replay rejection |
| Local attack surface | Loopback listener is an attack surface and must be bounded and authenticated |
| Windows | Existing Python/WebSocket and reconnect experience reduces uncertainty |
| Artifact lifetime | Survives Harness plugin reload; still ends with backend process or store eviction |
| Testability | Strong with fake authenticated server/client boundaries |
| Packaging | Clean split between npm plugin and Python backend, but two deployable units |

**INFERENCE / RECOMMENDATION:** Option B is preferred for the product and for
Windows desktop deployment. It preserves Python as the long-lived electronics
core and can later serve other trusted local adapters without embedding hardware
logic in them.

### Option C — rewrite HardwareToolRuntime in TypeScript

**PROJECT FACT:** The validated measurement workflow, deterministic analysis,
driver boundaries and Hardware Tool Runtime are Python implementations with real
DS1102Z-E HIL evidence.

**INFERENCE / RECOMMENDATION:** Reject Option C. Harness has no technical
restriction requiring a TypeScript electronics core. A rewrite would duplicate
validated behavior, split the contract authority and discard HIL confidence.

## 13. Recommended IPC architecture

```text
DeepSeek Harness / ctx.tools
            |
            | five native ToolDefinitions
            v
electronics-hardware plugin (TypeScript)
  - fixed alias map
  - projected Harness schemas
  - bounded renderer and adapter errors
  - no hardware logic
            |
            | AIA-HARNESS-HARDWARE Protocol v1
            | authenticated ws://127.0.0.1:<configured-port>
            v
Python Electronics Backend
  - independent auth/session/correlation state
  - strict five-operation allowlist
  - full Hardware Tool Schema validation
            |
            v
HardwareToolRuntime -> MeasurementService -> OscilloscopeInterface
```

**INFERENCE / RECOMMENDATION:** A new protocol namespace is required, for
example `aia-harness-hardware` v1. It may reuse reviewed implementation ideas
and generic primitives from the JLCEDA work, but it must not reuse the
`aia-jlceda` protocol, state machine, session registry, connection IDs, key or
business message schemas.

Candidate shared transport primitives are limited to:

- bounded JSON text framing;
- loopback-address enforcement;
- HMAC proof construction and constant-time comparison;
- nonce/challenge/session value objects;
- correlation tracking;
- reconnect/backoff scheduling;
- finite diagnostic redaction.

The Harness protocol must have its own:

- protocol name and version;
- pre-shared key or credential reference;
- challenge and session namespace;
- five-operation schema allowlist;
- message-size and request-duration budgets;
- pending request table and late/duplicate reply rejection.

Bind exactly to `127.0.0.1`, disable arbitrary remote exposure, use fresh
client/server nonces for every connection, bind sessions to their socket, reject
old sessions and proofs, and cap every message. The model must never supply the
endpoint, credential or IPC method.

For an in-flight request, the backend should retain a bounded operation record
by idempotency/request ID. Reconnect and duplicate delivery must return or await
that record rather than repeat the physical acquisition. This is necessary
before claiming safe cancellation or reconnect during measurement.

## 14. Five-tool request and result mapping

Each Harness definition supplies only its semantic arguments. The adapter adds
the frozen contract version and canonical operation before sending the request:

| Harness tool | Harness arguments | Canonical request operation |
|---|---|---|
| `hardware_get_status` | closed empty object | `hardware.get_status` |
| `hardware_measure_frequency` | `channel`, optional `context_id` | `hardware.measure_frequency` |
| `hardware_measure_vpp` | `channel`, optional `context_id` | `hardware.measure_vpp` |
| `hardware_capture_waveform` | `channel`, optional `context_id` | `hardware.capture_waveform` |
| `hardware_measure_pwm` | `channel`, optional `context_id` | `hardware.measure_pwm` |

**PROJECT FACT:** Current valid channels are constrained by the Hardware Tool
Contract; the model cannot provide resource name, SCPI, timeout, acquisition
format or driver settings.

**INFERENCE / RECOMMENDATION:** The canonical Harness output should retain the
complete Hardware Tool envelope:

```text
contract_version + ok + operation + result/error
```

This prevents the plugin from inventing a second measurement DTO. The renderer
may produce a smaller, model-facing representation, but it must retain quality,
warnings, units, observation source, provenance, coherence and artifact
metadata needed for correct interpretation.

## 15. Hardware error mapping

| Python runtime code | Harness treatment |
|---|---|
| `invalid_request` | Valid canonical `ok=false`; bounded request guidance |
| `unsupported_operation` | Valid `ok=false`, but also an adapter invariant violation because the map is static |
| `hardware_unavailable` | Valid canonical `ok=false`; backend/instrument unavailable |
| `instrument_connection_failed` | Valid canonical `ok=false`; no resource or provider details |
| `instrument_identity_mismatch` | Valid canonical `ok=false`; connected device is incompatible |
| `measurement_failed` | Valid canonical `ok=false` |
| `waveform_acquisition_failed` | Valid canonical `ok=false` |
| `analysis_failed` | Valid canonical `ok=false` |
| `artifact_unavailable` | Valid canonical `ok=false` |
| `internal_error` | Valid canonical `ok=false`; generic message only |
| IPC/auth/schema failure | Harness execution failure generated by the adapter |

**INFERENCE / RECOMMENDATION:** Never render SCPI, VISA resource strings,
Python paths, stack traces or backend exception text. An invalid output from the
Python boundary is an integration failure, not a measurement result.

## 16. Artifact compatibility

**PROJECT FACT:** Capture and PWM results expose finite ArtifactReference
metadata instead of waveform sample arrays. The current in-memory store uses
`memory://waveforms/...`; independent captures have distinct artifact IDs.

**OFFICIAL FACT:** Harness canonical values can contain nested objects, arrays
and strings, so ArtifactReference metadata is representable. Harness does not
automatically dereference project-defined URI schemes.

**INFERENCE / RECOMMENDATION:** It is safe to expose bounded artifact ID, URI,
media type, size/hash when present, capture metadata and point count. It is not
safe or necessary to put waveform arrays into the result. The Harness Agent
cannot use `memory://` as data without a future bounded artifact service/tool.
This is a documented limitation, not a reason to add artifact fetch in Phase 7B.

With Option B, the reference survives plugin reload while the Python backend
and in-memory entry remain alive. It does not survive backend restart, eviction
or transfer to another process.

## 17. Security implications

**OFFICIAL FACT:** Tool calls pass through pre-execute policy, monotonic guards,
execution wrappers, post-execute policy and result observation. Tool restriction
controls visibility but is explicitly not an authority boundary. Model-visible
content is represented in durable session history.

**INFERENCE / RECOMMENDATION:** Required controls are:

- use Native Tool mode only for this integration;
- do not expose model-generated TypeScript/Python orchestration for hardware;
- static five-tool and five-operation allowlists at both ends;
- no raw command, SCPI, VISA, filesystem path, Python command or arbitrary IPC
  method;
- user-controlled real/fake backend selection outside model arguments;
- pre-execute approval for enabling real hardware or the first real acquisition
  in a user-approved measurement context;
- monotonic guard for channel, connection state and local safety policy;
- no automatic retry of physical observations;
- masked serial number in model-facing rendering and presentation metadata;
- bounded logs with no secrets, full payload dumps or exception traces;
- separate Harness and JLCEDA credentials and sessions.

The plugin is trusted same-process Node code, not a sandboxed script. A renderer
mask protects model-visible/session content, not every same-process plugin
observer of the canonical value. If the serial number must be confidential from
all Harness plugins, the canonical value itself must be replaced with an
approved redacted projection; that policy requires a separate decision.

## 18. Compatibility gaps and decisions

| Gap | Severity | Decision before/within Phase 7B |
|---|---|---|
| Upstream master/release version skew | High | Pin one coherent released dependency set and compile-test it |
| Harness schema subset vs Draft 2020-12 contract | High | Generate and equivalence-test per-tool schema projections |
| Dotted canonical names rejected by DeepSeek API | High | Static underscore aliases; keep core names unchanged |
| Synchronous Python runtime vs async ToolDefinition | High | Async authenticated IPC adapter; Python runtime remains synchronous and serialized |
| No cooperative cancellation in hardware core | High | Omit `timeoutMs`; design quiescence/idempotency protocol before real HIL |
| Disconnect during an in-flight physical operation | High | Backend operation ledger; never replay acquisition blindly |
| `memory://` is process-local | Medium | Expose only metadata; document lifetime; no fetch tool yet |
| Serial number enters canonical output | Medium | Mask renderer; decide whether stronger canonical redaction is required |
| Harness session logs retain model-visible results | Medium | Bound and redact rendered content |
| Generic Harness retry policies could repeat measurements | High | Do not compose retries around hardware tools |
| Two local TypeScript integrations | Medium | Share primitives only; separate protocols, keys and sessions |
| Plugin/backend are separate deployables | Medium | Development patch first, prebuilt bundle and backend package later |

## 19. Proposed Phase 7B minimum

**INFERENCE / RECOMMENDATION:** Proceed only after explicit approval, in this
order:

1. Freeze an ADR covering version pins, five aliases, two-layer error semantics,
   cancellation/quiescence, rendering/redaction and independent IPC namespace.
2. Add contract tests that generate the five Harness parameter/output schema
   projections from the existing Hardware Tool Schema and reject drift.
3. Define only the versioned authenticated Harness Hardware transport envelope,
   handshake/state machine and five-operation request/response allowlist.
4. Implement a fake Python electronics backend and fake TypeScript IPC peer;
   verify authentication, replay rejection, correlation, message bounds,
   disconnect and duplicate-request behavior.
5. Implement the TypeScript plugin with five `defineTool` registrations and a
   fake IPC client. No VISA or real hardware.
6. Package it first as a monorepo development patch and run a manual Harness
   smoke test with the fake backend.
7. Only after those gates pass, connect the existing HardwareToolRuntime and
   perform separately authorized real HIL.

Phase 7B must not add Agent planning, teaching prompts, EDA orchestration, MCP,
new SCPI, new instruments, new analysis algorithms or arbitrary passthrough.

## 20. Review decision

**INFERENCE / RECOMMENDATION:** **Conditional GO for a narrow Phase 7B.**

Harness can faithfully carry the current result envelope, nested observations,
provenance, coherence, warnings, partial-success semantics and ArtifactReference
metadata. The Python core does not need to be rewritten. The integration is not
ready for direct implementation until the high-severity version, schema,
naming, cancellation and in-flight reconnect decisions above are frozen.

