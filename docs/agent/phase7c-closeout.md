# Phase 7C — Governed Agent Closeout

Status: **COMPLETE**.

Date: 2026-09-10.

Phase 7C established and validated the bounded authority and evidence chain for
real Agent-controlled measurement. It adds no authority for Phase 8 and does
not authorize another model request or hardware execution.

## Established controls

### 1. TrustedOperationScope

TrustedOperationScope defines which semantic operations a trusted user or host
workflow authorizes, on which channel, and with what invocation budget. Model
text, Tool arguments, Tool results, and simulated mode cannot create, widen, or
renew this scope. Missing, unknown, mismatched, or exhausted scope fails closed
before Physical Policy and IPC. Current budgeting is process-local, not durable
production authorization.

### 2. Physical Policy

Physical Policy independently determines whether a real physical operation is
confirmed and safe for the requested channel, target, voltage expectation,
grounding arrangement, and wiring state. Semantic authorization does not imply
physical authorization. A missing or mismatched trusted confirmation results in
zero IPC and zero hardware side effects.

### 3. Canonical Evidence and TeachingEvidenceContext

The canonical Hardware result records what was actually observed. Its bounded
TeachingEvidenceContext preserves execution state, instrument versus software
source, provenance, quality, warnings, sequential coherence, limitations, and
opaque artifact metadata. Design targets and prompt context cannot become
measurement evidence, and large waveform arrays remain outside the Agent
surface.

### 4. Grounding Guard

Grounding Guard determines which claims may be made from the trusted evidence.
It enforces exact semantic provenance or deterministic approved rounding and
unit conversion, source distinction, target-versus-observation separation,
quality and warning fidelity, sequential rather than atomic claims, opaque
artifact limits, and bounded inference. Unsupported candidates are discarded
without model retry, Tool retry, or remeasurement and are replaced only by a
deterministic fallback that passes Grounding itself. The guard validates a
constrained English claim surface; ambiguous or unrecognized free-form claims
fail closed.

### 5. Egress Guard

Egress Guard independently decides whether candidate text and Tool arguments
are safe to disclose. It prevents secrets, complete identifiers, VISA resource
strings, raw command-shaped instrument content, absolute host paths, waveform
arrays, and oversized output from crossing the durable or user-visible
boundary. Egress SAFE does not imply Grounding SUPPORTED, and Grounding
SUPPORTED does not replace Egress safety.

### 6. Runner Failure Boundary

The public validation runner is the outermost failure boundary. Static loading,
unexpected runtime failures, shutdown failures, and indeterminate execution
are converted to bounded categories and counters without exception messages,
stacks, paths, secrets, or blocked model content. Failure cannot cause model
retry, Tool retry, IPC replay, automatic remeasurement, or automatic budget
refund.

## Validated real chain

The final validated path is:

```text
real DeepSeek
→ official Harness AgentLoop
→ TrustedOperationScope
→ Physical Policy
→ governed semantic Hardware Tool
→ authenticated local IPC
→ real DS1102Z-E
→ canonical evidence / TeachingEvidenceContext
→ Egress Guard
→ Grounding Guard
→ safe grounded candidate or deterministic grounded fallback
```

Phase 7C.4F verified this path with one bounded status observation, one CH1
frequency measurement, and one CH1 PWM measurement. Extra model Tool
selections were denied before IPC, authorized budgets were not exceeded,
negative scenarios produced zero hardware effects, and no automatic retry or
remeasurement occurred. The frequency and PWM candidates both required
Grounding fallback; this was a PASS because the raw unsupported prose did not
escape and only independently verified fallback output was published.

## Historical evidence

The validation history remains intentionally immutable:

- Phase 7C.4: **NOT PASS**;
- Phase 7C.4B: **NOT PASS**;
- Phase 7C.4D first run: **NOT PASS**;
- Phase 7C.4D second run: **NOT PASS**;
- Phase 7C.4E: deterministic grounding repair **PASS**;
- Phase 7C.4F: final real governed validation **PASS**.

The earlier NOT PASS records were not rewritten after later controls succeeded.

## Boundary for the next phase

Phase 7C is complete. Phase 8 may design how EDA design evidence and Hardware
measurement evidence inform a Teaching/Diagnosis Agent, but no Phase 8 feature,
authority, Tool, or safety mechanism is implemented by this closeout.
