# AIA-JLCEDA Protocol v1

This directory is reserved for the normative JSON Schemas of AIA-JLCEDA Protocol
v1. Phase 1 creates the directory contract only; Phase 2 adds the first schemas.

`message.schema.json` will be the validation entry point once it is introduced.
Schemas define individual-message wire format only. Cross-message rules are defined
by `docs/architecture/aia-jlceda-v1-state-machine.md`.

The `fixtures` directory contains contract examples and negative cases. Fixtures
are test data, not a second protocol specification.

