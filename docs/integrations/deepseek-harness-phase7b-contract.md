# DeepSeek Harness Phase 7B Contract Baseline

Status: Phase 7B.1 and 7B.2 foundation only. No production plugin, socket,
Python server, Agent, EDA coordination, or hardware access is implemented.

## Architecture and version freeze

The accepted path is:

```text
DeepSeek Harness
  -> TypeScript hardware adapter (future)
  -> aia-harness-hardware/v1 authenticated localhost IPC (future transport)
  -> Python Electronics Backend
  -> HardwareToolRuntime -> MeasurementService -> hardware backend
```

The integration is frozen to the API shape reviewed at DeepSeek Harness commit
`d347e703908d0406b7a7ef80e3a0e594d86b2215`, labelled
`dsh@0.1.3-alpha.1`. Registry observation of
`@deepseek-ai/dsh@0.1.2-rc.1` is evidence of version skew, not a compatibility
claim. There is no supported semver range yet. The machine-readable fixture at
`protocols/harness-hardware/v1/compatibility/harness-api.fixture.json` makes
drift explicit without downloading floating upstream source in tests.

No Harness dependency is added in this phase because there is no production
plugin package to compile.

## Wire and state contracts

JSON Schema defines pre-auth `hello/challenge/prove/accepted/rejected` and
session `request/response/error/ping/pong` envelopes. The accompanying protocol
README freezes the HMAC input, nonce/expiry/session rules, message-size limit,
correlation, connection generation, delivery states, retry prohibition, and
cancellation meaning.

These are intentionally separate concerns:

- Schema rejects malformed individual messages, missing sessions, unrecognized
  types, unknown operations, and malformed canonical arguments.
- The semantic state layer rejects duplicate IDs, replayed challenges/proofs,
  unknown or duplicate responses, old sessions/generations, and late delivery.

The future server must bind exactly `127.0.0.1` and use a dedicated 256-bit PSK.
Secrets are not messages, tool arguments, logs, fixtures, or repository files.

All five operations use `NOT_SENT`, `SENT_UNCONFIRMED`, and
`RESPONSE_RECEIVED`. A disconnect from `SENT_UNCONFIRMED` is
`indeterminate_execution` and is never automatically replayed. A Harness abort
becomes `CLIENT_CANCELLED_WAIT`: it stops delivery to that caller but does not
claim the oscilloscope workflow was cancelled.

## Error layers

HardwareToolRuntime `ok=false` values are completed tool executions and retain
their canonical `error` object. They are not thrown by the future adapter.
Only authentication, protocol mismatch, unreachable backend, invalid response,
and indeterminate delivery are Harness adapter failures.

This distinction also preserves degraded `ok=true` measurements, warnings,
partial observations, coherence, provenance, and artifact evidence.

## Schema projection

`protocols/hardware/v1/hardware-tool.schema.json` remains the only canonical
Hardware Tool wire contract. The pure Python projector:

1. selects the canonical request arguments and operation-specific result;
2. resolves and inlines local `$ref` nodes;
3. specializes the measurement `allOf/oneOf` discriminator for one operation;
4. converts only a two-member nullable type union into Harness `oneOf`;
5. preserves objects, arrays, properties, required/optional fields, scalar
   enum/const, and boolean `additionalProperties`;
6. rejects every unrecognized keyword or unsafe merge;
7. emits an explicit sidecar manifest for approved constraints still enforced
   by the Python canonical validator.

Strict `project_schema()` has no deferred keywords and fails on any unsupported
validation keyword. The high-level hardware projection explicitly defers only
the reviewed non-structural set: `format`, `minLength`, `maxLength`, `minimum`,
`maximum`, `exclusiveMinimum`, `minItems`, `maxItems`, `uniqueItems`, and
`pattern`. They are never silently discarded: every occurrence is recorded
with JSON path, value, and the `python-canonical-validator` enforcement owner.
The Harness side therefore provides early structural validation; Python still
performs complete canonical validation before execution and on output.

Any new unsupported keyword, external/cyclic reference, `$ref` sibling,
non-null type union, schema-valued `additionalProperties`, changed discriminator,
or unsafe `allOf` merge fails projection and requires a compatibility review.

## Tool mapping

| Harness name | Canonical operation |
|---|---|
| `hardware_get_status` | `hardware.get_status` |
| `hardware_measure_frequency` | `hardware.measure_frequency` |
| `hardware_measure_vpp` | `hardware.measure_vpp` |
| `hardware_capture_waveform` | `hardware.capture_waveform` |
| `hardware_measure_pwm` | `hardware.measure_pwm` |

The underscore aliases satisfy the reviewed provider name restriction. The
dotted operation remains unchanged inside the request. There is no dynamic tool
name or operation passthrough.

## Output and artifact compatibility

The projected output is the complete operation-specific success envelope or
the complete canonical runtime error envelope. It retains `ok`, `operation`,
`result/error`, observations, quality, warnings, coherence, provenance, and all
ArtifactReference metadata. A renderer may summarize this later, but text is
not the only result representation.

Waveform sample arrays are not added. `memory://waveforms/<id>` is an opaque,
process-local reference that remains valid only while the owning Python backend
and entry remain alive. Harness must not dereference it. Phase 7B adds neither
`artifact.fetch` nor materialization.

## Security boundary

Protocol and projection both expose exactly five semantic operations. They
accept no command text, VISA resource, filesystem path, Python source, or
dynamic method. The compatibility layer imports no Rigol driver, PyVISA, SCPI,
analysis implementation, or MeasurementService implementation. The established
HardwareToolRuntime semantics are unchanged.
