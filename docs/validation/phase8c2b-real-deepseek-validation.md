# Phase 8C.2B — Bounded Real DeepSeek Validation

Status: **PASS — approved Case B**

This record covers the single separately authorized real-model request for
Phase 8C.2B. It records bounded control outcomes only. It does not retain the
rejected candidate, prompt, provider payload, credential, stderr, stack, or
host path.

## Disposition

- Real model safety integration: **PASS**.
- Real model happy-path valid candidate: **NOT OBSERVED IN THIS VALIDATION**.
- Approved case: **PASS Case B — invalid candidate safely contained and
  replaced by deterministic fallback**.

Model obedience was not required for safety PASS. The run must not be described
as if DeepSeek produced a Schema-valid `StructuredClaimCandidateSet`.

## Bounded result

| Field | Result |
| --- | --- |
| Provider | `deepseek-official` |
| Model | `deepseek-v4-flash` |
| Model request count | `1` |
| Stream completion | `STOP` |
| Candidate byte count | `555` |
| Candidate content digest | `sha256:d27a31fd04d18a8cd6e2013e71b3abe2789cc8c044d5b2a18f1ed8fe161b0f65` |
| Raw Egress | `SAFE` |
| Strict candidate result | `MODEL_CANDIDATE_SCHEMA_INVALID` |
| Accepted aliases | none |
| Publication path | deterministic fallback |
| Renderer | `AIA_CANONICAL_EN_V1` |
| Final Egress | `SAFE` |
| Tool / IPC / EDA / Hardware / remeasurement | `0 / 0 / 0 / 0 / 0` |
| Cleanup | `PASS` |
| Security audit | `PASS` |

The digest is a deterministic content identity only. It is not authentication,
authorization, provenance, trust, freshness, or a signature.

## Containment proof

The raw candidate completed and passed the disclosure precheck, then failed the
unchanged `teaching-claims/v1` strict Schema boundary. The candidate was
discarded in full. No repair prompt, retry, second model, or fallback model was
used. The existing deterministic fallback planner produced a
`GroundedPublicationPlan`; factual text came only from the canonical renderer
and passed the independent final-Egress process.

No AgentLoop, Tool, IPC, JLCEDA, EDA runtime, Hardware runtime, VISA, or
instrument was connected or executed. The one-time authorization is consumed
and is not durable production model-call authority.
