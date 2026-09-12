# Harness Publication Bridge v1

Private, inherited-stdio-only transport contracts between the trusted Python
publication Host and the two bounded TypeScript child processes used by Phase
8C.2B. These receipts are transport claims which Python validates; they are not
evidence, provenance, authorization, engineering truth, or Tool authority.

Each process receives exactly one UTF-8 JSON line and emits exactly one UTF-8
JSON line. SHA-256 values are deterministic content/correlation identities
only. They do not establish trust, freshness, authentication, or authority.

`request_digest` is calculated over the canonical JSON request object with the
`request_digest` member omitted. Failed and cancelled model receipts never
carry `raw_candidate`.
