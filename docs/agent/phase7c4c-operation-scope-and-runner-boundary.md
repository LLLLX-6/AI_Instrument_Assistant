# Phase 7C.4C — Trusted Operation Scope and Bounded Runner Boundary

Status: implemented for scripted/fake validation; pending architecture review. No real model or real instrument was used.

## Root causes

Phase 7C.4B had two independent containment gaps.

First, the physical hardware policy answered whether a measurement was physically safe, but no deterministic boundary answered whether the current trusted user workflow authorized the selected semantic operation. Prompt wording and a validation-only client counter could discourage or limit repeated calls, but neither represented request-scoped authorization.

Second, the real validation script caught failures only after its static module imports and maintained some counts after compatibility assertions. A module-load failure could therefore reach Node's default exception renderer, and an assertion could stop the scenario before exact bounded execution facts were persisted.

The historical Phase 7C.4B records remain NOT PASS. Missing frequency values and counts are not reconstructed.

## Trusted operation authorization model

`TrustedOperationScope` is a provider-neutral immutable value created only from trusted host/workflow state, deterministic application intent, or explicit validation configuration. It contains:

- a unique authorization scope ID;
- request correlation and workflow identity;
- a closed list of semantic operations with per-operation invocation budgets;
- an optional channel restriction;
- an optional bounded measurement intent;
- a trusted origin classification;
- an optional explicit user-authorization reference.

The closed semantic operation set is:

- `hardware.get_status`
- `hardware.measure_frequency`
- `hardware.measure_vpp`
- `hardware.capture_waveform`
- `hardware.measure_pwm`

There is no generic executor and no Driver, SCPI, VISA, Harness, LLM, IPC, Rigol, or JLCEDA object in the scope core.

The model cannot provide, alter, or enlarge this scope through prompt text or Tool arguments. If no trusted scope provider is configured, the production boundary supplies an empty fail-closed scope.

## Distinction from physical policy

Operation Scope answers: “Is this semantic operation authorized for this request and workflow?”

Physical Policy answers: “Is this physical setup safe, current, and explicitly confirmed?”

They are independent and both must pass. A SIMULATED backend still obeys Operation Scope. A REAL measurement additionally requires the existing physical policy confirmation. `hardware.get_status` is not globally exempt; it executes only when status is explicitly in scope.

## Frozen gate order

The Tool boundary executes in this order:

1. generated Tool JSON Schema validation;
2. non-consuming Operation Scope preflight;
3. physical policy context construction and evaluation;
4. atomic Operation Scope dispatch authorization and budget consumption;
5. IPC dispatch.

The preflight and final authorization are synchronous, with no asynchronous yield between them and physical policy evaluation. A scope denial therefore prevents physical-policy evaluation, IPC dispatch, and hardware side effects. The final authorization is immediately adjacent to IPC and is the only point that consumes budget.

## Scope decisions

The gate returns only `ALLOW` or `DENY` with one stable reason code:

- `allowed_operation_in_scope`
- `operation_not_authorized`
- `invocation_budget_exhausted`
- `channel_out_of_scope`
- `workflow_scope_mismatch`
- `unknown_operation`

Request-correlation mismatches are also classified as `workflow_scope_mismatch`, because both values form the trusted workflow correlation boundary.

## Invocation budget semantics

An allowed invocation consumes its per-operation budget when it crosses the final pre-IPC authorization point. Schema rejection, scope denial, and physical-policy rejection do not consume the authorized dispatch budget.

Once dispatch authorization is consumed, the budget is never refunded automatically. This includes `SENT_UNCONFIRMED` and indeterminate execution. The same scope cannot be used for an automatic retry or remeasurement. A new trusted authorization must create a new scope ID and therefore a new ledger entry.

The data model supports several explicitly authorized operations with independent finite budgets, although Phase 7C.4C validation scenarios mainly use one operation with budget one.

## Deterministic scenario behavior

For a CH1 frequency scope with budget one:

- one CH1 frequency call is allowed;
- PWM, Vpp, and waveform calls are denied before physical policy and IPC;
- CH2 frequency is denied;
- a second CH1 frequency call is denied as budget exhausted.

For a CH1 PWM scope with budget one, only one PWM call is allowed. Separate frequency or waveform calls are not implicitly authorized.

## Bounded runner failure boundary

`BoundedScenarioState` records Tool selections, IPC dispatches, confirmed physical measurements, model retries, Tool retries, and whether hardware execution did not occur, may have occurred, or is confirmed. Callers update this state before compatibility assertions.

`runWithBoundedFailureBoundary` maps known compatibility stops to a fixed category and every other exception to `UNEXPECTED_RUNNER_FAILURE`. The output contains only:

- phase and scenario identifiers;
- a fixed failure category;
- bounded integer counts;
- IPC-occurrence and hardware-execution state;
- model/Tool retry booleans;
- backend-shutdown state.

It never includes an exception message, stack, source path, model response, Tool arguments, or secret. Shutdown runs once for both success and failure; shutdown exceptions are themselves bounded.

The public real-agent runner is now a minimal dynamic-import wrapper. This is necessary because static dependency-loading failures occur before an imported module's own `try/catch`. The wrapper converts even module-load failure to one JSON stop record on stdout, leaves stderr empty, and suppresses Node's default uncaught stack.

Candidate Agent content still follows the existing candidate → Egress Guard → safe/fallback → report sequence. Teaching evidence, FACT/ANALYSIS/INFERENCE semantics, egress categories, deterministic fallback, and `HardwareToolRuntime` were not changed.

## Verification

The deterministic suite covers:

- all five static semantic operations and unknown-operation denial;
- frequency/PWM cross-operation denial;
- channel and workflow correlation;
- immutable trusted values and model attempts to enlarge scope or budget;
- budget exhaustion, indeterminate execution, and explicit new authorization;
- SIMULATED and REAL composition with physical ALLOW, REQUIRE_CONFIRMATION, and DENY;
- zero physical-policy, IPC, and hardware side effects after scope denial;
- known/unexpected runner failures, count persistence, uncertainty, shutdown, retry facts, secret/path/model-content containment, Egress Guard self-check, and subprocess stdout/stderr behavior;
- dependency boundaries and exact gate ordering.

All tests use scripted Agents, fake clients, and the simulated/fake backend. No `DEEPSEEK_API_KEY`, DeepSeek request, VISA connection, SCPI command, or DS1102Z-E access is part of this phase.

## Limitations

- This phase supplies the provider-neutral model, ledger, Harness integration seam, and deterministic validation configuration. A future trusted host workflow must issue and rotate scopes for production user requests.
- Invocation budgets are in-memory and scoped to one plugin process. Durable or distributed authorization accounting is not provided.
- Production host scope issuance, persistence, and recovery are NOT yet implemented; this process-local ledger must not be described as durable production authorization.
- The scope ID is the identity of one trusted authorization. Trusted issuers must never reuse an ID to represent expanded permissions; explicit reauthorization creates a new ID.
- No real DeepSeek or DS1102Z-E re-validation is performed until this change passes review.
