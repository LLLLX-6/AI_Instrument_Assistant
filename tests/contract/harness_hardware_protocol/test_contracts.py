from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_ROOT = ROOT / "protocols" / "harness-hardware" / "v1"
HARDWARE_SCHEMA = ROOT / "protocols" / "hardware" / "v1" / "hardware-tool.schema.json"
MESSAGE_SCHEMA = "https://aia.local/protocols/harness-hardware/v1/message.schema.json"


def load_case(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class HarnessHardwareProtocolContractTests(unittest.TestCase):
    def setUp(self) -> None:
        schema_paths = tuple(PROTOCOL_ROOT.rglob("*.schema.json")) + (HARDWARE_SCHEMA,)
        self.registry = SchemaRegistry.from_files(schema_paths)
        self.validator = SchemaValidator(self.registry)

    def test_all_valid_shared_fixtures_pass(self) -> None:
        paths = tuple(sorted((PROTOCOL_ROOT / "fixtures" / "valid").glob("*.case.json")))
        self.assertGreaterEqual(len(paths), 9)
        for path in paths:
            case = load_case(path)
            with self.subTest(path=path.name):
                result = self.validator.validate(case["schema_ref"], case["instance"])
                self.assertTrue(result.is_valid, result.errors)

    def test_all_invalid_shared_fixtures_fail(self) -> None:
        paths = tuple(sorted((PROTOCOL_ROOT / "fixtures" / "invalid").glob("*.case.json")))
        self.assertGreaterEqual(len(paths), 5)
        for path in paths:
            case = load_case(path)
            with self.subTest(path=path.name):
                result = self.validator.validate(case["schema_ref"], case["instance"])
                self.assertFalse(result.is_valid)

    def test_session_is_required_after_authentication(self) -> None:
        message = load_case(PROTOCOL_ROOT / "fixtures/valid/request-measure-pwm.case.json")["instance"]
        del message["session_id"]
        self.assertFalse(self.validator.validate(MESSAGE_SCHEMA, message).is_valid)

    def test_unknown_operation_and_malformed_arguments_are_rejected(self) -> None:
        valid = load_case(PROTOCOL_ROOT / "fixtures/valid/request-measure-pwm.case.json")["instance"]
        unknown = {**valid, "operation": "hardware.raw_scpi"}
        malformed = {**valid, "arguments": {"channel": 3}}
        self.assertFalse(self.validator.validate(MESSAGE_SCHEMA, unknown).is_valid)
        self.assertFalse(self.validator.validate(MESSAGE_SCHEMA, malformed).is_valid)

    def test_protocol_is_not_jlceda_protocol(self) -> None:
        valid = load_case(PROTOCOL_ROOT / "fixtures/valid/ping.case.json")["instance"]
        wrong = {**valid, "protocol": "aia-jlceda"}
        self.assertFalse(self.validator.validate(MESSAGE_SCHEMA, wrong).is_valid)

    def test_hardware_error_is_a_response_value_not_an_adapter_error(self) -> None:
        case = load_case(PROTOCOL_ROOT / "fixtures/valid/response-hardware-error.case.json")
        self.assertTrue(
            self.validator.validate(case["schema_ref"], case["instance"]).is_valid
        )
        self.assertEqual("response", case["instance"]["type"])
        self.assertFalse(case["instance"]["hardware_result"]["ok"])


if __name__ == "__main__":
    unittest.main()
