# AIA-JLCEDA Protocol v1

This directory is reserved for the normative JSON Schemas of AIA-JLCEDA Protocol
v1. Phase 1 creates the directory contract only; Phase 2 adds the first schemas.

`message.schema.json` is the validation entry point. Schemas define
individual-message wire format only. Cross-message rules are defined by
`docs/architecture/aia-jlceda-v1-state-machine.md`. The reviewed authenticated
business allowlist contains `eda.document.get_active`, `eda.selection.get`,
the additive read-only `eda.design.get`, and guarded `eda.view.highlight`.
`eda.design.get` returns a finite full-design projection; it never returns raw
provider objects or creates EDA mutation authority.

The `fixtures` directory contains contract examples and negative cases. Fixtures
are test data, not a second protocol specification.
