# Phase 7C.4E — Deterministic Response Grounding Boundary

Status: **PASS — deterministic response grounding boundary established**.

## Root cause

Phase 7C.4D demonstrated that deterministic authorization, physical safety, bounded Tool execution, canonical evidence projection, and egress disclosure controls can all pass while a model still produces a factually unsupported user-visible answer. Egress safety answers whether text may be disclosed; it does not establish that a number, source, quality statement, or engineering conclusion is supported by the evidence. The healthy second run therefore remained NOT PASS when model prose failed source distinction and no-fabrication checks.

This phase adds a separate post-egress Grounding Guard. It does not alter TrustedOperationScope, Physical Policy, HardwareToolRuntime, MeasurementService, the driver, SCPI, waveform analysis, IPC, Egress Guard semantics, or the canonical Hardware Schema.

## Boundary and trust model

The frozen output pipeline is:

1. buffer the candidate stream before durable Agent presentation;
2. apply Egress Guard to reasoning, Tool arguments, and final text;
3. when egress is safe and the stream is a final response, apply Grounding Guard;
4. publish the candidate only when grounding is `SUPPORTED`;
5. otherwise discard it and publish a deterministic evidence renderer;
6. inspect every fallback with both Egress Guard and Grounding Guard before publication.

Grounding authority is limited to provider-neutral `TeachingEvidenceContext`, a trusted `PolicyDecision` where execution state is relevant, and bounded host execution metadata already represented by those objects. Model reasoning, self-critique, citations, Tool arguments, raw driver state, and prior validation values are not evidence.

The Grounding core has no Harness, DeepSeek, IPC, driver, VISA, SCPI, Rigol, MeasurementService, JLCEDA adapter, or Egress implementation dependency. Harness-specific stream orchestration remains in the Agent adapter boundary.

## Claim and result model

The immutable result is `SUPPORTED` or `UNSUPPORTED`. An unsupported result contains only stable categories and bounded metadata (`claimKind` and an allowlisted/canonical evidence label). It never contains the rejected candidate text.

Stable categories are:

- `UNSUPPORTED_NUMERIC_CLAIM`
- `SOURCE_ATTRIBUTION_MISMATCH`
- `UNSUPPORTED_MEASUREMENT_CLAIM`
- `UNSUPPORTED_INFERENCE`
- `FALSE_AVAILABILITY_CLAIM`
- `FALSE_ATOMICITY_CLAIM`
- `ARTIFACT_ACCESS_OVERCLAIM`
- `QUALITY_MISREPRESENTATION`
- `WARNING_OMISSION_MATERIAL`
- `UNKNOWN_EVIDENCE_REFERENCE`

Claim extraction is deterministic and deliberately bounded. It recognizes numeric electronics claims, units, source labels, FACT/ANALYSIS/INFERENCE sections, explicit unavailability, quality language, material warning omission, atomicity language, and artifact-access language. Ambiguous measurement prose fails closed to the deterministic fallback; an LLM is never used as judge.

## Numeric grounding and deterministic display relation

Directly presented measurements must map to an evidence item with the same metric and source. Supported units are bounded to the current evidence slice: Hz/kHz, V/mV/Vpp, percent, seconds/milliseconds/microseconds, and artifact point count.

There is no proximity tolerance. The only permitted numeric relation is deterministic unit conversion followed by decimal display rounding at the precision explicitly written by the candidate. For example, evidence `10020.04 Hz` can be displayed as `10020.04 Hz`, `10020 Hz`, or `10.02 kHz`; `10.03 kHz` is rejected. Scientific notation and unrecognized units fail closed in this phase.

This same display relation supports the single bounded comparison inference. A stated `10 kHz / 30%` target may be described as broadly consistent only when the target exists in trusted request context and available observations round to the target at the target's stated precision. This is a qualitative comparison, not a tolerance or compliance claim.

## Provenance, target, and inference rules

- instrument observations remain `FACT / instrument`;
- software-derived observations remain `ANALYSIS / software_analysis`;
- simulated observations remain explicitly `simulated` and cannot be described as physical measurements;
- expected/design values remain target context and cannot become measured facts;
- an unavailable observation cannot be filled from a target, prior run, or another source;
- causal certainty such as a proven timer configuration or asserted root cause is unsupported;
- only an explicitly marked, non-causal “appears broadly consistent with the stated target” comparison is currently allowed.

When instrument and software values happen to be numerically equal, explicit source labelling still controls the claim. The guard does not infer provenance from equality alone.

## Quality, warnings, coherence, and artifacts

Canonical quality may be preserved but not upgraded: degraded/failed evidence cannot be called good, normal, reliable, or successful. For degraded evidence, a confident successful conclusion that omits any canonical material warning is rejected. The deterministic fallback always emits all canonical warnings, including unavailable evidence.

`sequential_same_session` may be described as sequential observations in one session; it cannot be described as simultaneous or atomic. `same_artifact` applies only to the software observations represented by that coherence field.

`ArtifactReference` remains opaque. The response may state that an artifact was captured and report bounded metadata such as `1200` points. It may state that samples were not inspected. Any claim to have read, inspected, accessed, or analyzed raw samples is rejected.

## Deterministic fallback and retry policy

The grounded fallback renders only bounded sections:

- `OBSERVED FACTS`
- `ANALYSIS`
- `QUALITY`
- `WARNINGS`
- `COHERENCE`
- opaque `ARTIFACT` metadata
- `LIMITATIONS`

It adds no free-form diagnosis. Failed or unknown executions produce no measurement numbers and do not borrow values from earlier runs. The output adapter self-checks fallback text through both Egress and Grounding; a fixed zero-evidence last resort exists only as defense in depth.

Grounding failure never asks the model to rewrite, regenerate, self-correct, call a Tool, or remeasure. Tests assert unchanged model-request, visible Tool-call, IPC-client-call, and physical-operation counts across fallback replacement.

## Recorded evidence fixtures

The successful fixture uses only the bounded Phase 7C.4D second-run measurements: instrument frequency `10020.04 Hz`, software frequency `10006.059835993472 Hz` (displayed safely as `10006.06 Hz` where requested), software duty `29.9541153263868%` (displayed as `29.9541%`), and instrument/software Vpp `0.4 V`, with quality good and no warnings. The simple frequency fixture records `10000 Hz`.

The degraded fixture preserves instrument frequency unavailable, instrument Vpp `0.016 V`, software frequency and duty unavailable, software Vpp `0.008 V`, mean `0.0036633333333333335 V`, RMS `0.005134199061197374 V`, and all three warnings: `signal_too_small`, `no_edges_detected`, and `instrument_frequency_unavailable`.

Fixture-only artifact identifiers and timestamps are synthetic test scaffolding and are not represented as recovered Phase 7C.4D runtime identifiers. No lost model candidate prose or missing execution value was reconstructed.

## Bounded-language and architecture limitations

This baseline checks a constrained English claim surface rather than claiming complete natural-language understanding. The model prompt now recommends one source-labelled numeric claim per line, but the prompt is advisory and the deterministic Guard remains authoritative. Unrecognized or ambiguous measurement semantics fail closed to fallback.

The claim grammar currently covers the Phase 7C.4D oscilloscope slice. Adding a new metric, unit, evidence source, language, artifact capability, or inference pattern requires an explicit reviewed extension and tests. The Grounding Guard is process-local and stateless; durable audit persistence, multilingual claim parsing, structured Harness response DTO enforcement, and generalized circuit diagnosis are not implemented here.

All Phase 7C.4, Phase 7C.4B, and both Phase 7C.4D records retain their historical NOT PASS verdicts. Phase 7C.4E does not rewrite them and does not itself run a real model or real hardware validation.
