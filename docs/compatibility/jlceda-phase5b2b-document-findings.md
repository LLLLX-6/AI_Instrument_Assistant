# JLCEDA Phase 5B.2b Active-Document Compatibility Findings

## Confirmed compatible behavior

The real JLCEDA Pro runtime supplies enough information to preserve the official
active-document identity and finite document type. The parent project UUID is
retained only when supplied. Provider-unavailable display names, project name,
document name, native revision, fingerprint and dirty state are represented as
null rather than synthesized.

Each successful read creates a new AIA observation token and capture timestamp.
The token is correlation metadata only: it is not a provider revision, content
version or stale-proof.

`tabId` remains extension-internal. Raw shape diagnostics and official runtime
objects do not cross the JSON protocol boundary.

## Real-runtime verification

On 2026-09-05 the real host passed active-document reading, identity preservation,
explicit unknown metadata, document switching, no-stale-cache behavior and the
no-active-document path. Detailed evidence classification is recorded in
`docs/manual-tests/jlceda-phase5b2b-real-runtime-observation-2026-09-05.md`.

## Remaining boundary

These findings apply only to `eda.document.get_active`. They do not establish
the reliability or semantic completeness of the selection or cross-probe APIs.
