# AIA Teaching Claims Candidate Protocol v1

This protocol is the wire-format authority for the minimal structured claim
candidate used by Phase 8C.2A. It is separate from Evidence v1, AIA-JLCEDA v1,
Hardware v1, and Harness-Hardware v1.

The candidate may only select and order request-local permission aliases. It
cannot supply claim text, values, units, sources, comparison semantics,
obligations, diagnosis, actions, or Tool fields.

`projection_id`, `context_fingerprint`, and `envelope_id` are deterministic
content identities only. Candidate values are untrusted claims that must be
matched against current Host-owned state. JSON Schema validates one wire
object; it does not establish authority, freshness, trust, alias ownership, or
cross-message lifecycle semantics.

Limits:

- raw candidate response: 16,384 UTF-8 bytes, enforced by the strict parser;
- selected permission references: 1 to 12;
- alias syntax: `p001` through `p999`;
- unknown properties and duplicate permission references are rejected.
