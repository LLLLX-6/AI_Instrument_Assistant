# Architecture Tests

Architecture tests introduced with production modules will inspect Python and
TypeScript dependency graphs and enforce allowed import directions. Syntax-aware
static analysis will enforce dangerous-API policy. Plain keyword searches are not
accepted as the primary architecture test mechanism.

Phase 1 reserves this test boundary; executable dependency rules begin when the
relevant modules are introduced in later phases.

