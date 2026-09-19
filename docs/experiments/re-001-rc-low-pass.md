# RE-001 — RC Low-Pass Reference Experiment

Status: **CORE E2E PROOF COMPLETE**. RE-001A is functionally complete with a
limited EDA provider; RE-001B Measurement Core is complete; RE-001C-Lite real
governed data flow is complete; and RE-001D-Lite real conversational E2E is
complete.

## Objective

Prepare one first-order RC low-pass experiment with a 1 kHz target cutoff.
The current slice reads a bounded complete schematic observation, recognizes
one series-resistor/shunt-capacitor topology, calculates deterministic theory,
and reports whether the design is ready for a later measurement slice.

## V1 circuit and assumptions

Required connectivity is `input -> resistor -> output -> capacitor -> reference`.
Identity comes from provider-neutral object references and pin-to-net
connectivity. Names such as Vin, Vout, and GND are presentation aids and do not
select the topology. The ideal model uses SI units and
`fc = 1 / (2*pi*R*C)`. Source and load resistance are never silently assumed;
when absent they are explicitly excluded. When supplied, source resistance is
added in series and load resistance is applied as the parallel resistance seen
by the capacitor. No pass/fail claim is made without an explicit tolerance.

## Responsibility boundary

The current provisional V1 EDA source is
`Yuanlitu MCP -> YuanlituMcpEDAAdapter -> DesignObservation`. The Adapter calls
only the three reviewed read operations, accepts `structuredContent`, and emits
a finite provider DTO. It derives network connectivity deterministically from
pin coordinates and wire geometry using the provider-reported coordinate
tolerance. Provider-local IDs and arbitrary attributes stop at this boundary.
The existing native JLCEDA adapter remains available but is not the provisional
RE-001 primary provider.

Deterministic code owns component values, connectivity, topology, node roles,
cutoff, and deviation. A future model may explain these facts or ask questions,
but cannot override them.

RE-001A emits design/theory evidence only. It emits no simulation evidence,
physical measurement, Scope, physical confirmation, Tool execution, or causal
diagnosis. SimulIDE integration remains deferred/optional. Later RE-001 slices
add measurement and conversational composition without changing this design
evidence boundary.

## Provider limitation

The full-design adapter uses documented component, pin, and wire read APIs.
Those JLCEDA APIs are currently BETA, and provider net refresh may be delayed.
The adapter therefore bounds object counts, checks document identity before and
after the observation, and fails closed on truncation or inconsistent state.
Real JLCEDA compatibility is not claimed by this offline slice. Yuanlitu exposes
no atomic provider revision and may omit explicit nets, so its generated
snapshot is observation identity only and its geometry-derived networks must
fail closed on malformed or ambiguous provider data.

The bounded real negative validation completed successfully through Yuanlitu
v0.1.1. A later positive validation stopped at the initial `easyeda_health`
call, before DTO mapping, geometry reconstruction, or experiment evaluation.
RE-001A is therefore functionally complete with a recorded provider-runtime
limitation; this phase does not attempt to debug or hide that limitation.

## RE-001B single-point measurement

RE-001B prepares exactly one 100 Hz sine-wave measurement point. The student
configures the signal source manually. The plan fixes CH1 to Vin and CH2 to
Vout, while the capacitor-side reference remains the circuit reference.
Automatic source control, frequency sweeping, cutoff search, and adaptive
measurement are outside this slice.

The plan accepts either node roles derived from a ready RE-001A observation or
explicit user-declared Vin/Vout/reference roles when the EDA provider is
unavailable. These provenance paths remain distinct. Neither one confirms that
a probe is physically connected or creates operation authorization.

Existing governed Hardware Tools remain responsible for status, frequency,
Vpp, and optional waveform capture. The Python experiment core only consumes
their existing typed results. It deterministically calculates
`gain_ratio = Vout_Vpp / Vin_Vpp`, `gain_db = 20*log10(gain_ratio)`, and numeric
frequency deviations. Physical measurements and software-derived gain remain
separate evidence. Without an explicit tolerance it emits no compliance result.

## RE-001C-Lite governed hardware data-flow slice

RE-001C-Lite adds a validation-only composition over the existing RE-001B
measurement plan and analyzer. Four independent Harness-owned operation scopes
authorize, in fixed order, frequency and Vpp on CH1 followed by frequency and
Vpp on CH2. Two separate trusted physical confirmations bind Vin to CH1 and
Vout to CH2. A failure stops the remaining sequence; no retry, sweep, waveform
capture, or model action is permitted.

The Python boundary validates each canonical Hardware response against the
existing Hardware v1 schema and additionally binds the expected semantic
operation and channel. Successful physical values become existing immutable
`MeasurementResult` values with `INSTRUMENT` observation provenance. A
schema-valid `ok=false` response becomes a bounded typed operation failure,
not an IPC exception and not invented measurement evidence. Only successfully
mapped results enter `RCSinglePointMeasurementAnalyzer`, which remains the sole
owner of gain and frequency-deviation calculations.

This slice defines no public protocol and changes none of Hardware canonical,
Harness-Hardware v1, Evidence v1, AIA-JLCEDA v1, or Interactive v1. Its scope
and confirmation objects remain process-local validation authority, not durable
production authorization.

The separately authorized real validation completed all four one-shot
operations without retry. It observed CH1/CH2 frequency of 10020.04 Hz and Vpp
of 0.34 V / 3.24 V. These values are point-in-time physical evidence, not
production constants and not an RC-filter performance result. The resulting
ratio and frequency deviations came only from the existing deterministic
analyzer. No tolerance or causal conclusion was introduced.

## RE-001D-Lite conversational composition

RE-001D-Lite adds only a two-stage validation composition. A constrained
Host-side intent recognizer accepts the reviewed natural-language request and
prepares the existing user-declared 100 Hz single-point plan plus deterministic
wiring instructions. Its output contains no Scope, physical confirmation,
Tool arguments, or execution authority. Completion accepts only the existing
governed RE-001C receipt, whose four exact one-shot Scope, Physical Policy,
IPC, operation/channel, and canonical-result bindings are validated before any
model request.

Strictly mapped `MeasurementResult` objects feed the existing analyzer. Their
physical facts and deterministic software analyses are projected into the
existing `TeachingDiagnosisContext`. The existing structured-candidate,
Grounding, deterministic renderer/fallback, and final-Egress boundaries then
control publication. The model can select Host-owned permission aliases only;
it cannot supply factual prose, numeric values, authority, or troubleshooting
conclusions. Potential source configuration, probe attenuation, or channel
setup explanations remain explicitly unresolved questions and are never
promoted to physical facts or causal diagnosis.

This phase adds no public protocol and performs no automatic retry, waveform
capture, sweep, EDA action, arbitrary SCPI, or direct experiment-layer VISA
access. The separately authorized final real validation completed the entire
bounded conversational chain with four real one-shot measurements and one
DeepSeek request. The model candidate was not trusted for direct publication;
deterministic grounded fallback passed final Egress and preserved the observed
10040.16 Hz frequencies and 0.40 V / 3.92 V amplitudes without claiming a
cause. See the [final RE-001D-Lite validation](../validation/re001d-lite-final-real-conversational-e2e.md).

## Milestone disposition

- RE-001A: **FUNCTIONALLY COMPLETE / EDA PROVIDER LIMITED**.
- RE-001B: **COMPLETE — MEASUREMENT CORE**.
- RE-001C-Lite: **COMPLETE — REAL GOVERNED DATA-FLOW PROVEN**.
- RE-001D-Lite: **COMPLETE — REAL CONVERSATIONAL E2E PROVEN**.
- Overall: **CORE E2E PROOF COMPLETE**.

This milestone does not claim a full RC sweep, automated signal generation,
complete simulation or EDA integration, full RC physical performance, report
export, generalized diagnosis, or production-ready generalized lab automation.
Reliable native JLCEDA selection, Yuanlitu positive-provider runtime
validation, the SimulIDE bridge, signal-generator control, automatic frequency
sweep, cutoff search, full RC physics validation, report export, and
generalized diagnosis remain deferred or optional and do not block the core
milestone.
