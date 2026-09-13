# JLCEDA Extension Workspace

Phase 8.5B adds the offline-reviewed JLCEDA official-Dialog companion while
preserving the earlier authenticated read-only provider operations and guarded
highlight. Official API access remains isolated behind the finite DTO/runtime
boundary. Agent, LLM, instrument access, raw dispatch, and design mutation are
absent.

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

Product endpoint ownership:

- `127.0.0.1:49624`: AIA-JLCEDA v1 provider gateway;
- `127.0.0.1:49625`: Hardware backend, never interactive traffic;
- `127.0.0.1:49626` by default: separately authenticated interactive Host,
  configurable from the official `Configure Connection` dialog.

JLCEDA external-interaction permission is required for the two WebSocket
connections. Only the non-secret interactive port is stored in extension user
settings. Credentials are entered through password dialogs and are not echoed
or persisted by the extension.

The interaction client enters an explicit synchronization state after hello
acceptance and becomes connected only after the authoritative Host snapshot.
Later Status refreshes are session/generation-bound. Selection notifications
are coalesced and generation-bound; a change during synchronization produces
one current-state Host refresh after synchronization rather than an event
history replay. The first real Phase 8.5B smoke remains NOT PASS, and no retry
is authorized by this documentation.

Phase 8.5B production authority is intentionally limited to exact design
selection through the Python Host. If operation authorization or physical
setup is pending, the JLCEDA surface shows a bounded instruction to continue in
the DeepSeek Harness and sends no Challenge answer. It never constructs
`TrustedOperationScope` or `ProbeSetupConfirmation`.
