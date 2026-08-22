# Contract Fixture Format

Fixtures are shared by the Python and TypeScript contract-test suites. They are
test data, not protocol specifications.

Each `*.case.json` file contains:

- `description`: human-readable test intent;
- `schema_ref`: the normative schema `$id` or fragment under test;
- `instance`: the wire-format JSON value being validated.

Directory placement defines the expectation: files below `valid/` must validate,
while files below `invalid/` must fail validation.
