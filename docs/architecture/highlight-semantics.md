# Highlight semantic contract

Submission and effect verification are separate facts. ACCEPTED means a
provider acknowledged submission; UNVERIFIED makes no claim about visible
rendering. Provider true never establishes VERIFIED_APPLIED. Provider false
is REJECTED or a provider error, never NOOP. Verified targets require actual
evidence and must be a subset of submitted targets. InMemory verification
refers only to its controlled simulated state, never to real editor pixels.

STRONG_REQUIRED is the default. Missing or unsupported fingerprint scope
requires strong_guard_unavailable before a view effect. A finite fingerprint
protects only its declared projection, never the whole design. Snapshot IDs
are observation tokens, not revisions. WEAK_IDENTITY_CHECK is opt-in and
checks current provider/document identity and target resolution only.

Wire-to-network expansion requires explicit permission. Results report the
actual guard and expansion. TTL None, provider_default style, and
replace_existing None express no provider-specific presentation guarantee.
False explicitly requests non-replacement; adapters unable to guarantee it
must reject it along with unsupported TTL/style/replacement.

Idempotency uses a key plus canonical command. Same key/same command returns
the stored result without repeating effects; different commands conflict.
Timeout or disconnect after submission starts leaves execution indeterminate.
Never automatically replay. Idempotency records have a process-lifetime
boundary; an application must not interpret restart as permission to replay.

Wire schemas describe message-local structure. Domain enforces target
membership and shared observation invariants. Adapters enforce runtime
capabilities, guard checks, idempotency, and truthful evidence.
