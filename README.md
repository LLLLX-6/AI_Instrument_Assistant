# AI Instrument Assistant

AI Instrument Assistant is a Python-centered electronic design and instrument
analysis system.

The repository is currently implementing JLCEDA Integration V0.2. This phase is
contract-first and deliberately excludes real JLCEDA APIs, WebSocket networking,
agents, LLMs, VISA, SCPI, EDA mutation, and arbitrary JavaScript execution.

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

