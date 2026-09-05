# ADR-0002: Keep the EDA Domain Provider-Neutral and Evidence-Oriented

- Status: Accepted
- Date: 2026-08-20

## Context

The first integration targets JLCEDA, while the Python domain must remain usable by
future KiCad and Altium adapters. Measurements may also originate from instruments
that do not produce waveforms.

## Decision

The JLCEDA wire contract fixes its provider to `jlceda-pro`, but provider-specific
runtime details do not enter `DesignDocument`. They are recorded as provenance or
integration metadata.

`ProbeTarget` contains proposed probe semantics only. Physical connection
confirmation is a separate `ProbeConnectionConfirmation` referenced by
`MeasurementContext`.

`MeasurementContext` references general evidence and results. Large artifacts are
represented by `ArtifactReference`; completion does not require a waveform.

Provider-neutral selection kinds include document, net, wire, component and
other. `provider_kind` may retain a bounded provider-native classification for
diagnostics, but never a provider runtime object. A selected wire and a derived
network are distinct references.

An observed `CircuitNet` may have an empty endpoint tuple when connectivity is
unresolved. Empty endpoints do not assert a known zero-endpoint topology. Derived
nets must share the selection provider, document and AIA observation token, but
their references need not be members of the selected primitive set.

## Consequences

- Domain code is not coupled to JLCEDA naming or runtime objects.
- A future multimeter measurement can complete with scalar evidence.
- Probe guidance and human confirmation have distinct audit histories.
- Partial provider observations remain representable without inventing graph
  connectivity or collapsing selected primitives into semantic networks.
