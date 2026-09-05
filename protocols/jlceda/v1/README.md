# AIA-JLCEDA Protocol v1

This directory is reserved for the normative JSON Schemas of AIA-JLCEDA Protocol
v1. Phase 1 creates the directory contract only; Phase 2 adds the first schemas.

`message.schema.json` is the validation entry point. Schemas define
individual-message wire format only. Cross-message rules are defined by
`docs/architecture/aia-jlceda-v1-state-machine.md`. Phase 5B.1 freezes only the
handshake and heartbeat allowlist; EDA business operations are intentionally absent.

The `fixtures` directory contains contract examples and negative cases. Fixtures
are test data, not a second protocol specification.
