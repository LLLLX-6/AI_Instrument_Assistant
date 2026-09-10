# AIA Engineering Evidence Protocol v1

This directory is the language-neutral wire-format authority for approved
teaching and engineering evidence exchange. TypeScript and Python code are
bindings/adapters; neither language type system is the cross-language authority.

`TeachingEvidenceContext` preserves the Phase 7C behavior: evidence kind,
source, quality, warnings, provenance, coherence, failure semantics, unavailable
values, and opaque artifact handling. The canonical artifact reference is reused
from Hardware v1 through `$ref`; this protocol adds no Hardware fields.

## Compatibility policy

- Required fields and existing meanings are frozen for v1.
- Compatible additions must be optional, documented, and accepted deliberately
  by both bindings before release.
- Renames, removals, new required fields, enum narrowing, or semantic changes
  require a new explicit schema version.
- Schema shape validation does not replace domain invariants or trusted
  cross-message/workflow evidence such as physical probe confirmation.

`EngineeringEvidenceContext` is a composed immutable view, not a source of
truth. Its `inferences` collection is required to be empty in Phase 8A.2.
