# Phase 5B.3b Remote Selection — Manual Runtime Evidence

Evidence source: the user's Phase 5B.3b closeout report in the development
conversation. These are user-executed tests in a real JLCEDA Professional
runtime, not tests executed by the automated suite or independently by the
development agent. Exact execution date, editor version, runtime environment,
project/document identity, and imported archive hash were not supplied.
The delivered extension for this phase was v0.2.9; the report does not
independently identify the installed archive.

## Reported results

| Scenario | User-reported result |
| --- | --- |
| Empty selection | PASS |
| Wire selection | PASS |
| Component selection | PASS |
| Multiple selection | PASS |
| Provider primitive identity/type mapping | PASS |
| Derived net metadata | No invented endpoint, source, or expectation |
| Boundary data | No raw primitive leakage observed |
| Selection freshness | No stale cached selection observed |

These results accept the Phase 5B.3b read-only selection slice. The final
freshness observation applies to the reported runs only. AIA snapshot IDs
continue to represent observation tokens, not atomic provider snapshots,
revisions, or strong stale guards.

## Evidence limits

The report does not separately confirm unsupported primitives, unnamed wires,
selection-limit rejection, or the document-switch race. Their existing
automated coverage must not be relabeled as actual runtime observations.
It contains no claim about highlight rendering, target resolution for
cross-probe, TTL, styles, or replacement semantics.

## Automatic closeout verification

The closeout reruns Python tests, shared TypeScript contract tests,
TypeScript runtime/architecture tests, strict typechecking, and the package
build. Their results are reported separately in the closeout response.
Fake-runtime tests establish bounded data and controlled execution, but do
not establish real-editor visual behavior.
