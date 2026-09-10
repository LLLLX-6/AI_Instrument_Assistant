from __future__ import annotations

import json
import unittest
from pathlib import Path

from ai_instrument_assistant.integrations.deepseek_harness.evidence_contract import (
    EVIDENCE_CONTEXT_SCHEMA_ID,
    EvidenceContractBinding,
)
from ai_instrument_assistant.protocol.fixture_loader import FixtureLoader
from ai_instrument_assistant.protocol.schema_validator import SchemaInstanceValidationError


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "protocols" / "evidence" / "v1" / "fixtures"


class EvidenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.binding = EvidenceContractBinding.from_repository(ROOT)

    def test_all_shared_valid_fixtures_are_accepted(self) -> None:
        fixtures = FixtureLoader(FIXTURES).load("valid")
        self.assertGreaterEqual(len(fixtures), 2)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.path.name):
                self.assertTrue(
                    self.binding.validator.validate(
                        fixture.schema_ref, fixture.instance
                    ).is_valid
                )

    def test_all_shared_invalid_fixtures_are_rejected(self) -> None:
        fixtures = FixtureLoader(FIXTURES).load("invalid")
        self.assertGreaterEqual(len(fixtures), 4)
        for fixture in fixtures:
            with self.subTest(fixture=fixture.path.name):
                self.assertFalse(
                    self.binding.validator.validate(
                        fixture.schema_ref, fixture.instance
                    ).is_valid
                )

    def test_python_binding_preserves_current_semantics_and_round_trips(self) -> None:
        payload = json.loads(
            (FIXTURES / "valid" / "pwm-teaching-context.case.json").read_text(
                encoding="utf-8"
            )
        )["instance"]
        context = self.binding.parse_teaching_context(payload)

        self.assertEqual(context.facts[0].category.value, "PHYSICAL_FACT")
        self.assertEqual(context.analyses[0].category.value, "SOFTWARE_ANALYSIS")
        self.assertAlmostEqual(context.analyses[1].value.percent, 29.95)
        self.assertTrue(context.artifact.opaque)
        self.assertEqual(context.artifact.reference.uri, "memory://waveforms/pwm-out-1")
        self.assertEqual(context.warnings, tuple(payload["warnings"]))
        self.assertEqual(
            context.coherence.instrument_vs_software,
            "sequential_same_session",
        )
        self.assertEqual(
            self.binding.to_wire(context), payload
        )
        self.assertEqual(self.binding.schema_id, EVIDENCE_CONTEXT_SCHEMA_ID)

    def test_unavailable_observation_is_not_upgraded(self) -> None:
        payload = json.loads(
            (FIXTURES / "valid" / "unavailable-teaching-context.case.json").read_text(
                encoding="utf-8"
            )
        )["instance"]
        context = self.binding.parse_teaching_context(payload)
        self.assertIsNone(context.facts[0].value)
        self.assertEqual(context.facts[0].quality.value, "unavailable")

    def test_binding_rejects_unvalidated_malformed_wire(self) -> None:
        with self.assertRaises(SchemaInstanceValidationError):
            self.binding.parse_teaching_context({"requestedGoal": "partial"})

    def test_artifact_reference_is_reused_from_hardware_v1(self) -> None:
        schema = json.loads(
            (
                ROOT / "protocols" / "evidence" / "v1" /
                "teaching-evidence-context.schema.json"
            ).read_text(encoding="utf-8")
        )
        artifact = schema["$defs"]["opaqueArtifact"]
        self.assertEqual(
            artifact["properties"]["reference"]["$ref"],
            "https://aia.local/protocols/hardware/v1/hardware-tool.schema.json#/$defs/artifact",
        )
        self.assertNotIn("artifact_id", artifact["properties"])
        self.assertNotIn("uri", artifact["properties"])


if __name__ == "__main__":
    unittest.main()
