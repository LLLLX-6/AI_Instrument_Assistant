# JLCEDA Phase 5A Compatibility Findings

Reviewed on 2026-08-22 against the current official documentation, the
`easyeda/pro-api-sdk` main branch, `@jlceda/pro-api-types`, and the official
`easyeda/eext-run-api-gateway` reference extension.

## Frozen compatibility baseline

- Official SDK scaffold: `pro-api-sdk` 1.6.17 (reviewed at commit
  `874bd9d`).
- SDK Node requirement: `>=20.17.0`.
- Extension engine compatibility: `^3.2.0`, matching the current SDK template.
- API type declarations: exact `@jlceda/pro-api-types` 0.4.14, matching the
  lockfile of the reviewed SDK revision.
- Local build runtime: Node 24.18.0 and npm 11.16.0.

Future SDK or type upgrades require a dedicated compatibility review and
real-editor smoke test; package ranges are not allowed to advance this boundary
silently.

## API findings

1. `eda.dmt_SelectControl.getCurrentDocumentInfo()` is BETA. It returns only
   document type, document UUID, tab ID, and optional parent project/library
   UUID. It does not provide a document name, native revision, snapshot ID, or
   content fingerprint. The adapter therefore does not invent those values or
   map this DTO directly into the Python Domain.
2. `eda.sch_SelectControl.getAllSelectedPrimitives()` is BETA and is the current
   replacement for deprecated `getSelectedPrimitives()`. The adapter uses only
   the current method and reports it as unavailable rather than silently
   falling back.
3. `eda.sch_SelectControl.doCrossProbeSelect()` is currently documented as a
   public API. The frozen 0.4.14 declaration models a synchronous boolean while
   newer generated official reference material models an asynchronous boolean.
   It is the only Phase 5A view action and is called through a static semantic
   allowlist with `highlight=true` and `select=false`.
4. `ISCH_PrimitiveWire.getState_Net()` is public, but the official 0.4.14 type
   declaration warns that its global net value can be stale while asynchronous
   multi-page net refresh is pending. A reported net name is diagnostic input,
   not a revision or whole-design truth.
5. Selection objects are official primitive class instances rather than stable
   JSON records. Real-editor validation found that calling
   `getState_PrimitiveId()` on a selected schematic wire can incorrectly enter
   a PCB initialization path and throw. The adapter therefore obtains IDs from
   `SCH_SelectControl.getAllSelectedPrimitives_PrimitiveId()` and never reads
   identity from the primitive proxy. It rejects mismatched ID/object counts
   instead of guessing an association. Both selection methods are BETA.
   The adapter otherwise extracts only primitive type and the currently
   supported semantic key (wire net or component designator), caps selection
   output at 128 objects, and never returns the primitive.
6. The 0.4.14 declaration bundle compiles with the project's strict TypeScript
   configuration without disabling declaration-file checking.
7. The official SDK lockfile currently pins `esbuild` 0.24.2. `npm audit`
   reports GHSA-67mh-4wv8-2f99 against its development server. Phase 5A invokes
   esbuild only as a one-shot local bundler and does not start that server;
   `npm audit --omit=dev` is clean, and neither esbuild nor any package manager
   dependency enters the `.eext`. Updating this official-tooling pin should be
   reviewed when the SDK moves beyond 0.24.2.
8. The frozen 0.4.14 type declaration models
   `SCH_SelectControl.doCrossProbeSelect()` as returning a synchronous boolean,
   while the current official generated reference models it as
   `Promise<boolean>`. The adapter awaits the result, which is compatible with
   both forms. A true result records API acceptance only; the API exposes no
   read-back capability that proves a visible highlight was rendered.
9. Real-editor validation showed that cross-probe can return true without a
   visible schematic-canvas change. This remained true after build 0.2.4
   captured selected primitive IDs, cleared the selected overlay, and then
   applied cross-probe highlight. The selected overlay is therefore not a
   sufficient explanation for the missing visual effect. If cross-probe returns
   false or throws, the adapter makes a best-effort restoration of the original
   selection. These calls change view state only and do not mutate design
   content.
10. For the tested runtime, `view.highlight` is classified as
    `available-but-behaviorally-unverified` (degraded): the API entry point is
    present and accepts a one-net request, but its visual behavior was manually
    observed as ineffective. It must not be advertised as reliably applied.
    This is a runtime-scoped finding, not a claim that every JLCEDA version or
    every cross-document scenario is unsupported.

The detailed manual evidence record is
[`jlceda-phase5a-real-runtime-observation-2026-08-23.md`](../manual-tests/jlceda-phase5a-real-runtime-observation-2026-08-23.md).

## Safety decision

The official `eext-run-api-gateway` was consulted only for extension lifecycle,
manifest, packaging, and future reconnect design. Its remote-code execution
path is intentionally excluded. This project has no WebSocket in Phase 5A and
permanently prohibits `eval`, `Function` constructors, backend-supplied source,
element-access method dispatch, and design create/modify/delete/save calls.

## Sources

- https://prodocs.lceda.cn/cn/api/guide/
- https://prodocs.lceda.cn/cn/api/guide/stability.html
- https://prodocs.lceda.cn/cn/api/reference/pro-api.dmt_selectcontrol.getcurrentdocumentinfo.html
- https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_selectcontrol.html
- https://prodocs.lceda.cn/cn/api/reference/pro-api.sch_selectcontrol.docrossprobeselect.html
- https://github.com/easyeda/pro-api-sdk
- https://github.com/easyeda/eext-run-api-gateway
