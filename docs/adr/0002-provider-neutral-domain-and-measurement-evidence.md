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

## Consequences

- Domain code is not coupled to JLCEDA naming or runtime objects.
- A future multimeter measurement can complete with scalar evidence.
- Probe guidance and human confirmation have distinct audit histories.

