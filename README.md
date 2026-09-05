# AI Instrument Assistant

AI Instrument Assistant is a Python-centered electronic design and instrument
analysis system.

The repository is currently implementing JLCEDA Integration V0.2. Phase 5B.1
provides a real JLCEDA read-only runtime boundary plus an authenticated
localhost WebSocket transport for handshake and heartbeat. EDA business
operations are not yet carried over that transport. Agents, LLMs, VISA, SCPI,
EDA mutation and arbitrary JavaScript execution remain excluded.

## Phase 1 test commands

Python tests use the standard-library test runner:

```text
python -m unittest discover -s tests -p "test_*.py"
```

TypeScript tests use the Node.js built-in test runner with native type stripping:

```text
npm test
```

The JSON Schemas under `protocols/jlceda/v1/` will become the single source of
truth for wire-format structure in Phase 2. Cross-message behavior is governed
separately by the protocol state machine documentation.
