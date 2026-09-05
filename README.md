# AI Instrument Assistant

AI Instrument Assistant is a Python-centered electronic design and instrument
analysis system.

The repository is currently implementing JLCEDA Integration V0.2. Phase 5B.2b
adds the first authenticated read-only vertical slice,
`eda.document.get_active`, over the hardened localhost transport. Remote
selection and highlight are not enabled. Agents, LLMs, VISA, SCPI, EDA mutation
and arbitrary JavaScript execution remain excluded.

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
