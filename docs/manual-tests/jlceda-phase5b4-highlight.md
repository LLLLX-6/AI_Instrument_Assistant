# Phase 5B.4b — guarded remote highlight manual smoke test

Status: RUN in actual JLCEDA; completion reported by the user on 2026-09-06.
The user did not include the individual A–E outputs in the closeout message, so
their detailed outcomes remain explicitly unreported rather than inferred.

## Preparation

1. Import `extensions/jlceda/build/dist/ai-instrument-assistant_v0.2.10.eext`.
   About must show 0.2.10. Reload the extension if necessary.
2. Keep the existing secret in `.aia-secrets/jlceda-psk.txt`; do not log/share it.
3. Stop any previous standalone gateway/script using port 49624. Each command
   below starts its own gateway on the SAME 127.0.0.1:49624 endpoint and stops
   it when finished. Do not run run_jlceda_gateway.py concurrently.
4. Open a schematic and select the object BEFORE running the command.
5. Within 30 seconds, use AI Instrument Assistant → Configure Backend Connection
   with the existing secret (or let bounded reconnect succeed). If retries were
   exhausted between runs, configure again. `--connect-timeout 120` allows more
   time without changing reconnect policy.
6. Open the JLCEDA Console. The fixed `guarded cross-probe invocation` log counts
   provider calls, not visible effects. The old local Highlight Selection menu
   is informational only; it is NOT the remote test entry.

All commands run from the repository root in PowerShell.

## A — default strong guard

Select a wire, then run:

```powershell
.venv\Scripts\python.exe scripts\highlight_jlceda_selection.py
```

Expected: strong_guard_unavailable, no provider-call log and no view side effect.
Python rejects locally because the real provider has no supported fingerprint.
The matching Extension enforcement is covered by automated direct-wire tests.

## B — weak guard, no expansion permission

```powershell
.venv\Scripts\python.exe scripts\highlight_jlceda_selection.py --weak-identity-check
```

For a wire that requires network-level cross-probe: scope_expansion_required,
no provider-call log and no view effect. A wire without a net may instead return
unsupported_target. This is an honest rejection, not a fabricated network.

## C — weak guard and explicit wire-to-net expansion

Select a wire on a known network such as PWM_OUT:

```powershell
.venv\Scripts\python.exe scripts\highlight_jlceda_selection.py --weak-identity-check --allow-scope-expansion
```

If the official API returns true, expect accepted/unverified, wire_to_net,
the original wire identity in submitted_targets, an empty verified_applied_targets
list and expires_at=null. False means rejected, never noop. Manually record
whether any visible change occurred; even visible changes do not automatically
change the program's verification status. Accepted without a visible change is
a compatibility observation, not proof that the contract was violated.

## D — component

Select one component with a known unique designator; run command B. Expected:
accepted/unverified with scope_expansion=none if the provider accepts. Missing,
unsupported or duplicate designators produce structured errors with no call.
Confirm the view action targets the resolved designator, not a primitive ID.

## E — idempotency

Select a wire and clear the Console before this run:

```powershell
.venv\Scripts\python.exe scripts\highlight_jlceda_selection.py --weak-identity-check --allow-scope-expansion --repeat
```

The script sends the same command twice through TWO Python adapter instances
on one authenticated gateway, so the second response exercises the Extension
ledger rather than merely Python's cache. Expect identical results and exactly
ONE `guarded cross-probe invocation` Console line. A changed command with the
same key must report idempotency_conflict. If the first outcome is indeterminate,
the script skips repeat; do not manually replay it with a new key.

## Evidence to return

Record editor version/environment, extension version, A–E PASS/FAIL, finite
result/error text, provider-call count, visible view observations and unexpected
Console errors. Do not include secrets or huge raw objects. If a connection
is lost after invocation, record indeterminate and whether reconnect recovers;
do not claim that timeout proves nonexecution. No Phase 5B.4b commit until review.

## Actual runtime observation — 2026-09-06

The user reported that the real JLCEDA manual smoke test was completed. No
secret, raw provider object, Console transcript, A–E status table, or specific
return value was supplied with that report.

The three evidence dimensions are therefore recorded independently:

| Evidence dimension | Recorded fact |
|---|---|
| Provider submission response | Not reported; do not infer accepted or rejected |
| Program verification status | No runtime result supplied; implementation remains UNVERIFIED for JLCEDA |
| Human-observed visible effect | Not reported; do not infer visible or invisible |

This closeout does not promote a human observation into
`VERIFIED_APPLIED`. Even if a visible effect was observed during the test, it
would remain separately recorded manual evidence; the program has no supported
read-back mechanism that verifies exact visible application to requested
targets.
