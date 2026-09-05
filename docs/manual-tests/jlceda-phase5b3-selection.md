# JLCEDA Phase 5B.3b Remote Selection Manual Smoke Test

The user has accepted the tested read-only slice. Reported runtime outcomes
and evidence limits are recorded in
[the manual evidence record](jlceda-phase5b3b-real-runtime-observation.md).

## Scope

This test validates only the authenticated read-only `eda.selection.get`
vertical slice. It does not validate remote highlight, design mutation, Agent,
LLM, or instrument behavior.

## Preconditions

- Import the Phase 5B.3b `.eext` built from this workspace.
- Keep the pre-shared secret in `.aia-secrets/jlceda-psk.txt`; never paste it
  into logs or commit it.
- Open a schematic in JLCEDA Professional.

## Procedure

1. Select a schematic wire whose visible network name is known.
2. In the repository root, run:

   ```powershell
   .venv\Scripts\python.exe scripts\get_jlceda_selection.py
   ```

3. In JLCEDA choose **AI Instrument Assistant → Configure Backend Connection**
   and enter the shared secret if the Extension is not already reconnecting.
4. Confirm the script prints one selected object with `object_type=wire`, its
   official primitive ID as `native_id`, and its provider type as
   `provider_kind=Wire`.
5. If a non-empty network name was observed, confirm a separate derived net is
   present with `native_id=null`, no endpoints, no source, and no signal
   expectation. This means connectivity is unresolved; it does not mean a
   zero-endpoint network was proven.
6. Repeat with an empty selection, a component, an unsupported primitive type,
   a wire with no observed network name, and a small multiple selection.
7. During one run, switch documents while the selection is being read. If this
   race is hit, the request must fail with `inconsistent_observation`; it must
   not return a mixed snapshot.

## Expected safety properties

- The same newly generated AIA `snapshot_id` appears on the document reference,
  every selected object, and every derived net in one response.
- The token marks one coherent observation window. It is not an atomic provider
  snapshot, provider revision, content version, or stale-proof.
- `totalSelected`, `truncated`, primitive summaries, raw official objects,
  `tabId`, fake endpoints, fake source pins, and fake signal expectations do
  not cross into the wire response or Python Domain.
- More than 128 selected primitives produces a bounded error rather than a
  silently partial Domain selection.

Record actual editor version, selected primitive types, pass/fail results, and
any finite error text separately from automated-test evidence.
