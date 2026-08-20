# ADR-0001: Separate Wire Schema from Protocol State Machine

- Status: Accepted
- Date: 2026-08-20

## Context

A JSON Schema can validate the structure of one JSON value but cannot prove that a
message was received in a legal protocol state, belongs to the authenticated
session, uses a fresh nonce, or correctly correlates with an earlier message.

## Decision

JSON Schemas under `protocols/jlceda/v1/` are the single source of truth for
wire-format structure. Cross-message behavior is defined in a separate protocol
state machine and verified by semantic state-machine tests.

Messages are divided into pre-authentication and session classes. Pre-authentication
handshake messages do not require `session_id`. An accepted handshake creates the
session, after which every heartbeat and business message requires that session.

## Consequences

- Structural validation and semantic validation are separate steps.
- A schema-valid message may still be rejected by the state machine.
- Phase 3 must include transition, correlation, nonce, replay, and session tests.

