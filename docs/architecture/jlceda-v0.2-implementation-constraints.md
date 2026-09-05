# JLCEDA Integration V0.2 Implementation Constraints

This document records implementation boundaries for V0.2. It is not a second
wire-protocol specification.

## Contract ownership

- JSON Schema owns wire-format structure only.
- The protocol state machine owns cross-message semantics.
- Python domain models own domain invariants after transport mapping.
- TypeScript transport DTOs and Python transport DTOs must be derived from or
  validated against the same schemas.

## Version and fingerprint semantics

- `native_revision` is supplied by an EDA provider and may be null.
- `snapshot_id` is an AIA-generated observation token used to correlate one
  capture. It is not a provider revision, a content version, or stale-proof.
- `DesignDocument.fingerprint` is either null when a meaningful content
  projection is unavailable, or a complete immutable `DesignFingerprint`
  containing its value, scope kind, scope version, and included paths.
- A content fingerprint must never be described as the state of an entire EDA
  project unless its declared scope actually covers that project.

## Provider neutrality

- The JLCEDA wire protocol may fix `provider` to `jlceda-pro`.
- Python EDA domain models must use a provider-neutral identifier/value type and
  remain reusable by future KiCad and Altium adapters.
- Adapter and runtime information belongs to provenance or integration metadata,
  not `DesignDocument`.

## Measurement boundaries

- Probe connection confirmation is represented by an independent
  `ProbeConnectionConfirmation` and referenced by `MeasurementContext`.
- `ProbeTarget` describes where and how to probe; it does not assert that a user
  connected a probe.
- Measurement completion is based on general evidence and results. It does not
  globally require a waveform artifact.
- Large data is referenced through `ArtifactReference`, never embedded in
  `MeasurementContext`.

## Test and source boundaries

- Fake EDA adapters and the TypeScript `FakeEdaPeer` live under test support, not
  production source paths.
- Dangerous API detection uses syntax-aware static analysis.
- Layering is enforced by architecture/dependency tests over import graphs.
- Plain keyword grep is not an architectural correctness mechanism.

## Explicit V0.2 exclusions

- LLM and Agent implementations
- VISA and SCPI
- real JLCEDA Extension API calls
- real EDA mutation
- arbitrary JavaScript execution
- real localhost WebSocket transport
