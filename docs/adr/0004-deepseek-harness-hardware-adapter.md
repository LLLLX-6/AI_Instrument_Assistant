# ADR-0004: Use Persistent Authenticated Localhost IPC for DeepSeek Harness

- Status: Accepted
- Date: 2026-09-06
- Contract: `aia-harness-hardware/v1`

## Context

AI Instrument Assistant already has a Python electronics core whose
HardwareToolRuntime, MeasurementService, waveform analysis, VISA path, and
DS1102Z-E driver have automated and real HIL evidence. DeepSeek Harness plugins
run in TypeScript under Cordis and have a reload lifecycle different from the
desired lifetime of measurements and in-memory artifacts.

The reviewed Harness baseline is developer preview commit
`d347e703908d0406b7a7ef80e3a0e594d86b2215`, source context
`dsh@0.1.3-alpha.1`. The observed npm package is
`@deepseek-ai/dsh@0.1.2-rc.1`; compatibility between those versions has not
been established.

## Decision

Choose **B: persistent authenticated localhost IPC**:

```text
DeepSeek Harness
  -> TypeScript electronics hardware plugin
  -> authenticated aia-harness-hardware/v1 on 127.0.0.1
  -> persistent Python Electronics Backend
  -> HardwareToolRuntime -> MeasurementService -> hardware backend
```

The TypeScript plugin owns only five static Tool registrations, projected
Harness schemas, request serialization, an IPC client, bounded adapter-error
mapping, and model-facing rendering. It contains no SCPI, VISA, Rigol driver,
analysis, MeasurementService logic, or arbitrary IPC invocation.

This retains the HIL-validated Python core, keeps artifact lifetime independent
of Cordis reload, establishes a clear concurrency and trust boundary, behaves
predictably on Windows desktop, and allows the electronics backend to serve
other explicitly trusted local adapters.

## Alternatives

### A. Spawn a Python subprocess

Rejected for production. Process ownership is useful for tests and development
helpers, but Harness reload would also reset Python state and in-memory artifact
lifetime. Locating Python and handling Windows process trees also becomes plugin
policy. This option may be used only by explicit test/development tooling.

### C. Rewrite the Python core in TypeScript

Rejected. Harness does not require it, it would duplicate the hardware and
analysis behavior, split contract authority, and discard existing automated and
real HIL evidence.

## Consequences

- The Python backend is a separately supervised, long-lived deployable.
- IPC must use an independent 256-bit PSK, fresh challenges, isolated sessions,
  strict correlation, bounded messages, and a static five-operation allowlist.
- A sent-but-unconfirmed request is never replayed and is reported as
  `indeterminate_execution`.
- Harness cancellation initially means only `CLIENT_CANCELLED_WAIT`; it does not
  assert physical measurement cancellation.
- Canonical `ok=false` hardware results remain successful Harness values. Only
  IPC/adapter failures use Harness failure semantics.
- The canonical Hardware Tool JSON Schema remains authoritative. Harness
  schemas are deterministic projections, not a second hand-written contract.
- This ADR authorizes no socket or production plugin implementation in Phase
  7B.1/7B.2.
