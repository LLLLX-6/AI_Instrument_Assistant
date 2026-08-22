# JLCEDA Extension Workspace

Phase 5A is a real, read-only JLCEDA Pro extension runtime. It validates the
official `eda.*` API to normalized Transport DTO boundary without a Python
Backend, WebSocket, Agent, LLM, or design mutation.

Compatibility baseline:

- pro-api-sdk: 1.6.17
- JLCEDA EDA engine: ^3.2.0
- @jlceda/pro-api-types: 0.4.14 (exact pin)
- Node.js: >=20.17.0; validated locally with Node 24.18.0

Commands:

- `npm run test:contracts` keeps shared JSON Schema contract verification
  isolated from the extension runtime.
- `npm run test:adapter` runs the fake official runtime and architecture safety
  tests.
- `npm run build` type-checks and creates the importable `.eext` under
  `build/dist/`.

Only `src/runtime/jlc-eda-api-adapter.ts` may call official EDA services. The
packager uses an explicit two-file allowlist (`extension.json` and the bundled
`dist/index.js`) so tests, source files, and protocol fixtures do not enter the
extension archive.
