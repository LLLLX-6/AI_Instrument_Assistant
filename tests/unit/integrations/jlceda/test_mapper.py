from __future__ import annotations

import copy
import unittest
from pathlib import Path
from typing import get_type_hints
from uuid import UUID

from ai_instrument_assistant.domain.eda.models import DesignObjectRef
from ai_instrument_assistant.integrations.jlceda.errors import (
    UnvalidatedWireDataError,
    WireToDomainMappingError,
)
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.protocol.fixture_loader import FixtureCase, FixtureLoader
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import (
    SchemaInstanceValidationError,
    SchemaValidator,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROTOCOL_ROOT = REPOSITORY_ROOT / "protocols" / "jlceda" / "v1"


class JLCEDADomainMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        registry = SchemaRegistry.from_directory(PROTOCOL_ROOT)
        cls.validator = SchemaValidator(registry)
        cls.fixtures = FixtureLoader.from_protocol_root(PROTOCOL_ROOT)
        cls.mapper = JLCEDADomainMapper()

    def valid_fixture(self, parent: str, filename: str) -> FixtureCase:
        return next(
            fixture
            for fixture in self.fixtures.load("valid")
            if fixture.path.parent.name == parent and fixture.path.name == filename
        )

    def test_valid_document_wire_maps_to_design_document(self) -> None:
        fixture = self.valid_fixture(
            "design-document",
            "native-revision-null.case.json",
        )
        validated = self.validator.validate_and_freeze(
            fixture.schema_ref,
            fixture.instance,
        )

        document = self.mapper.map_design_document(validated)

        self.assertEqual("STM32_Test", document.project_name)
        self.assertEqual("main_schematic", document.document_name)
        self.assertEqual("jlceda-pro", document.document_ref.provider)
        self.assertEqual(
            UUID("11111111-1111-4111-8111-111111111111"),
            document.snapshot_id,
        )
        self.assertIsNone(document.native_revision)

    def test_document_fingerprint_scope_maps_without_loss(self) -> None:
        fixture = self.valid_fixture(
            "design-document",
            "native-revision-null.case.json",
        )
        validated = self.validator.validate_and_freeze(
            fixture.schema_ref,
            fixture.instance,
        )

        document = self.mapper.map_design_document(validated)
        wire_fingerprint = fixture.instance["fingerprint"]

        self.assertEqual(wire_fingerprint["value"], document.fingerprint.value)
        self.assertEqual(wire_fingerprint["scope_kind"], document.fingerprint.scope_kind)
        self.assertEqual(wire_fingerprint["scope_version"], document.fingerprint.scope_version)
        self.assertEqual(
            tuple(wire_fingerprint["included_paths"]),
            document.fingerprint.included_paths,
        )

    def test_partial_provider_metadata_maps_without_fabrication(self) -> None:
        fixture = self.valid_fixture(
            "design-document",
            "partial-provider-metadata.case.json",
        )
        validated = self.validator.validate_and_freeze(
            fixture.schema_ref,
            fixture.instance,
        )

        document = self.mapper.map_design_document(validated)

        self.assertIsNone(document.document_ref.display_name)
        self.assertIsNone(document.project_id)
        self.assertIsNone(document.project_name)
        self.assertIsNone(document.document_name)
        self.assertIsNone(document.native_revision)
        self.assertIsNone(document.fingerprint)
        self.assertIsNone(document.is_dirty)
        self.assertEqual("pcb", document.document_type)

    def test_valid_pwm_selection_maps_to_selection_context(self) -> None:
        fixture = self.valid_fixture("selection-context", "pwm-out.case.json")
        validated = self.validator.validate_and_freeze(
            fixture.schema_ref,
            fixture.instance,
        )

        context = self.mapper.map_selection_context(validated)

        self.assertEqual("PWM_OUT", context.selection.primary_object.display_name)
        self.assertEqual("U1", context.nets[0].source.component_reference)
        self.assertEqual("PA0", context.nets[0].source.pin_name)
        self.assertEqual(10_000.0, context.nets[0].signal_expectation.frequency_hz)
        self.assertAlmostEqual(
            0.30,
            context.nets[0].signal_expectation.duty_cycle.ratio,
        )
        self.assertAlmostEqual(
            30.0,
            context.nets[0].signal_expectation.duty_cycle.percent,
        )

    def test_valid_full_design_maps_connectivity_without_losing_identity(self) -> None:
        fixture = self.valid_fixture("design-observation", "rc-low-pass.case.json")
        validated = self.validator.validate_and_freeze(
            fixture.schema_ref, fixture.instance
        )

        observation = self.mapper.map_design_observation(validated)

        self.assertEqual(2, len(observation.components))
        self.assertEqual(3, len(observation.nets))
        self.assertEqual(
            observation.nets[1].ref,
            observation.components[0].pins[1].net_ref,
        )
        self.assertTrue(observation.nets[2].is_reference)

    def test_full_design_mapper_rejects_unvalidated_wire(self) -> None:
        fixture = self.valid_fixture("design-observation", "rc-low-pass.case.json")
        with self.assertRaises(UnvalidatedWireDataError):
            self.mapper.map_design_observation(fixture.instance)  # type: ignore[arg-type]

    def test_domain_provider_is_an_ordinary_string_not_a_literal(self) -> None:
        self.assertIs(str, get_type_hints(DesignObjectRef)["provider"])

    def test_mapper_rejects_unvalidated_wire_data(self) -> None:
        fixture = self.valid_fixture(
            "design-document",
            "native-revision-null.case.json",
        )

        with self.assertRaises(UnvalidatedWireDataError):
            self.mapper.map_design_document(fixture.instance)  # type: ignore[arg-type]

    def test_malformed_wire_is_rejected_before_mapper(self) -> None:
        fixture = self.valid_fixture(
            "design-document",
            "native-revision-null.case.json",
        )
        malformed = copy.deepcopy(fixture.instance)
        malformed["source_runtime"] = "raw-extension-object"

        with self.assertRaises(SchemaInstanceValidationError):
            self.validator.validate_and_freeze(fixture.schema_ref, malformed)

    def test_cross_object_domain_violation_becomes_mapping_error(self) -> None:
        fixture = self.valid_fixture("selection-context", "pwm-out.case.json")
        inconsistent = copy.deepcopy(fixture.instance)
        inconsistent["selection"]["selected_objects"] = []
        validated = self.validator.validate_and_freeze(
            fixture.schema_ref,
            inconsistent,
        )

        with self.assertRaises(WireToDomainMappingError):
            self.mapper.map_selection_context(validated)


if __name__ == "__main__":
    unittest.main()
