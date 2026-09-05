# JLCEDA Phase 5B.2b Active Document Manual Smoke Test

This test validates one real read-only path: JLCEDA's current-document API to a
provider-neutral Python `DesignDocument`. It does not enable remote selection,
highlight, EDA mutation, Agent, LLM, VISA or SCPI.

## Preconditions

- Import the newly built `ai-instrument-assistant-0.2.8.eext` into JLCEDA Pro.
- Open a schematic, PCB, symbol, footprint, home or blank editor document.
- Keep the 43-character secret from `.aia-secrets/jlceda-psk.txt` private.

## Procedure

1. From the repository root, run:

   `.venv\Scripts\python.exe scripts\get_jlceda_active_document.py`

2. In JLCEDA choose **AI Instrument Assistant → Configure Backend Connection**.
3. Paste the same 43-character backend secret.
4. Wait for the `backend authenticated` toast.
5. Observe the Python terminal. It should print one normalized document and then
   stop its gateway.

## Expected result

- `provider` is `jlceda-pro`.
- `document_id` and `native_id` are the official document UUID.
- `canonical_id` is deterministically scoped by provider and document UUID.
- `project_id` is the official parent project UUID when supplied, otherwise null.
- Provider-unavailable names, revision, fingerprint and dirty state are null.
- `snapshot_id` is a new AIA observation token, not a content version or stale proof.
- `captured_at` is the AIA observation timestamp.
- `tabId`, raw shape diagnostics and official runtime objects are absent.

If no design document is active, the script must report the structured
`NoActiveDocumentError` path rather than constructing placeholder metadata.
