# ADR-0003: Keep Test Doubles Out of Production and Enforce Boundaries Structurally

- Status: Accepted
- Date: 2026-08-20

## Context

V0.2 requires Fake EDA behavior but must not accidentally ship test peers or rely on
fragile text searches to enforce architecture.

## Decision

Python Fake EDA support and TypeScript `FakeEdaPeer` live under test support paths.
Dangerous API rules will use syntax-aware static analysis. Module layering will use
architecture/dependency tests that inspect imports and package relationships.

## Consequences

- Production builds cannot import test peers through normal package entry points.
- Comments and documentation cannot create false dangerous-API failures.
- Architecture violations are detected from dependency relationships rather than
  arbitrary keyword presence.

