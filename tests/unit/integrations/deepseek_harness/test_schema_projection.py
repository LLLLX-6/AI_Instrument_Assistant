from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from ai_instrument_assistant.integrations.deepseek_harness.schema_projection import (
    HARNESS_TOOL_OPERATION_MAP,
    ProjectionError,
    project_hardware_tools,
    project_schema,
)


ROOT = Path(__file__).resolve().parents[4]
CANONICAL_PATH = ROOT / "protocols/hardware/v1/hardware-tool.schema.json"


def canonical() -> dict:
    return json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))


def pwm_output(*, kind: str = "pwm", ok: bool = True) -> dict:
    if not ok:
        return {
            "contract_version": "1.0", "ok": False,
            "operation": "hardware.measure_pwm",
            "error": {"code": "hardware_unavailable", "message": "offline", "details": {}},
        }
    return {
        "contract_version": "1.0", "ok": True,
        "operation": "hardware.measure_pwm",
        "result": {
            "request_id": "123e4567-e89b-12d3-a456-426614174000", "kind": kind,
            "channel": 1, "context_id": None,
            "instrument": {"manufacturer": "RIGOL", "model": "DS1102Z-E", "serial_number": "masked", "firmware_version": "1"},
            "waveform": {
                "artifact": {"artifact_id": "123e4567-e89b-12d3-a456-426614174001", "uri": "memory://waveforms/1", "media_type": "application/vnd.aia.waveform+json", "size_bytes": 1200, "sha256": "a" * 64},
                "channel": 1, "point_count": 1200, "sample_interval_seconds": 2e-7,
                "time_range_seconds": [-0.1, 0.1], "voltage_range_v": [-0.3, 0.3],
                "acquisition_mode": "normal", "captured_at": "2026-01-01T00:00:00Z",
            },
            "observations": {}, "quality": "good", "warnings": [],
            "coherence": {"software_observations": "same_artifact", "instrument_vs_software": "sequential_same_session"},
            "provenance": {"started_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:00:01Z", "analysis_algorithm": {"name": "aia.threshold_edges", "version": "1.0.0"}},
        },
    }


class SchemaProjectionTests(unittest.TestCase):
    def test_const_scalar_types_are_inferred_for_frozen_harness(self) -> None:
        cases = (
            ("ready", "string"),
            (7, "integer"),
            (2.5, "number"),
            (True, "boolean"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                projected = project_schema({"const": value}).schema
                self.assertEqual(expected, projected["type"])

    def test_boolean_const_is_not_inferred_as_integer(self) -> None:
        self.assertEqual("boolean", project_schema({"const": False}).schema["type"])

    def test_homogeneous_enum_scalar_types_are_inferred(self) -> None:
        cases = (
            (["good", "degraded"], "string"),
            ([1, 2, 3], "integer"),
            ([1.0, 2.5], "number"),
            ([True, False], "boolean"),
        )
        for values, expected in cases:
            with self.subTest(values=values):
                projected = project_schema({"enum": values}).schema
                self.assertEqual(expected, projected["type"])

    def test_ambiguous_or_non_scalar_enums_fail_closed(self) -> None:
        for values in (
            ["good", 1],
            [1, True],
            [None, "x"],
            [{"kind": "x"}],
            [[1], [2]],
            [],
        ):
            with self.subTest(values=values):
                with self.assertRaises(ProjectionError):
                    project_schema({"enum": values})

    def test_null_and_non_finite_const_fail_closed(self) -> None:
        for value in (None, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ProjectionError):
                    project_schema({"const": value})

    def test_explicit_type_and_existing_one_of_are_not_rewritten(self) -> None:
        explicit = {"type": "string", "const": "ready"}
        one_of = {"oneOf": [{"type": "null"}, {"type": "string"}]}
        self.assertEqual(explicit, project_schema(explicit).schema)
        self.assertEqual(one_of, project_schema(one_of).schema)

    def test_strict_projection_resolves_nested_local_refs(self) -> None:
        source = {
            "$defs": {"inner": {"type": "string"}, "outer": {"type": "array", "items": {"$ref": "#/$defs/inner"}}},
            "type": "object", "properties": {"values": {"$ref": "#/$defs/outer"}},
            "required": ["values"], "additionalProperties": False,
        }
        result = project_schema(source)
        self.assertEqual("array", result.schema["properties"]["values"]["type"])
        self.assertEqual("string", result.schema["properties"]["values"]["items"]["type"])
        self.assertEqual(["values"], result.schema["required"])
        self.assertFalse(result.schema["additionalProperties"])

    def test_optional_nullable_const_nested_objects_and_arrays_are_preserved(self) -> None:
        source = {
            "type": "object", "additionalProperties": False, "required": ["operation", "nested"],
            "properties": {
                "operation": {"const": "hardware.measure_pwm"},
                "optional": {"type": ["string", "null"]},
                "nested": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "integer"}}}},
            },
        }
        result = project_schema(source).schema
        self.assertNotIn("optional", result["required"])
        self.assertEqual("hardware.measure_pwm", result["properties"]["operation"]["const"])
        self.assertEqual({"string", "null"}, {item["type"] for item in result["properties"]["optional"]["oneOf"]})
        self.assertEqual("integer", result["properties"]["nested"]["properties"]["items"]["items"]["type"])

    def test_unsupported_keyword_and_semantic_loss_are_rejected(self) -> None:
        with self.assertRaises(ProjectionError):
            project_schema({"type": "string", "minLength": 1})
        with self.assertRaises(ProjectionError):
            project_schema({"type": "string", "pattern": "^[a-z]+$"}, allowed_deferred_keywords=frozenset({"minLength"}))
        with self.assertRaises(ProjectionError):
            project_schema({"$ref": "https://example.invalid/schema.json"})

    def test_canonical_operation_drift_fails_closed(self) -> None:
        changed = canonical()
        changed["$defs"]["measurementRequest"]["properties"]["operation"]["enum"].append(
            "hardware.measure_resistance"
        )
        with self.assertRaises(ProjectionError):
            project_hardware_tools(changed)

    def test_five_static_non_dotted_harness_mappings_are_generated(self) -> None:
        tools = project_hardware_tools(canonical())
        self.assertEqual(5, len(tools))
        self.assertEqual(set(HARNESS_TOOL_OPERATION_MAP), {tool.harness_name for tool in tools})
        self.assertFalse(any("." in tool.harness_name for tool in tools))
        self.assertEqual(set(HARNESS_TOOL_OPERATION_MAP.values()), {tool.canonical_operation for tool in tools})

    def test_parameters_preserve_status_and_measurement_shapes(self) -> None:
        tools = {tool.canonical_operation: tool for tool in project_hardware_tools(canonical())}
        status = tools["hardware.get_status"].parameters_schema
        pwm = tools["hardware.measure_pwm"].parameters_schema
        self.assertEqual([], status.get("required", []))
        self.assertFalse(status["additionalProperties"])
        self.assertEqual(["channel"], pwm["required"])
        self.assertIn("context_id", pwm["properties"])
        self.assertEqual([1, 2], pwm["properties"]["channel"]["enum"])

    def test_output_keeps_full_success_error_and_artifact_structure(self) -> None:
        tool = next(t for t in project_hardware_tools(canonical()) if t.canonical_operation == "hardware.measure_pwm")
        serialized = json.dumps(tool.output_schema, sort_keys=True)
        for marker in ("observations", "quality", "warnings", "coherence", "provenance", "artifact", "sha256"):
            self.assertIn(marker, serialized)
        validator = Draft202012Validator(tool.output_schema)
        self.assertEqual([], list(validator.iter_errors(pwm_output())))
        self.assertEqual([], list(validator.iter_errors(pwm_output(ok=False))))

    def test_operation_kind_mismatch_stays_rejected_by_canonical_contract(self) -> None:
        schema = canonical()
        validator = Draft202012Validator({"$ref": "#/$defs/runtimeMeasurementSuccess", "$defs": schema["$defs"]})
        self.assertGreater(len(list(validator.iter_errors(pwm_output(kind="frequency")))), 0)

    def test_partial_result_and_artifact_reference_are_not_replaced_with_waveform_arrays(self) -> None:
        tools = {tool.canonical_operation: tool for tool in project_hardware_tools(canonical())}
        output = tools["hardware.capture_waveform"].output_schema
        encoded = json.dumps(output, sort_keys=True)
        self.assertIn("artifact_id", encoded)
        self.assertIn("uri", encoded)
        self.assertNotIn("voltage_values", encoded)
        self.assertNotIn("time_values", encoded)

        degraded = pwm_output()
        degraded["operation"] = "hardware.capture_waveform"
        degraded["result"]["kind"] = "waveform"
        degraded["result"]["waveform"] = None
        degraded["result"]["quality"] = "degraded"
        degraded["result"]["warnings"] = ["capture metadata unavailable"]
        self.assertEqual([], list(Draft202012Validator(output).iter_errors(degraded)))

    def test_generated_schemas_contain_only_reviewed_harness_keywords(self) -> None:
        allowed = {
            "type", "title", "description", "properties", "required",
            "additionalProperties", "items", "oneOf", "enum", "const", "default",
        }

        def inspect(node: object) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertIn(key, allowed)
                    if key == "properties":
                        for child in value.values():
                            inspect(child)
                    elif key in {"items", "oneOf"}:
                        inspect(value)
            elif isinstance(node, list):
                for child in node:
                    inspect(child)

        for tool in project_hardware_tools(canonical()):
            inspect(tool.parameters_schema)
            inspect(tool.output_schema)

    def test_projection_is_deterministic_and_records_every_deferred_constraint(self) -> None:
        first = project_hardware_tools(canonical())
        second = project_hardware_tools(canonical())
        self.assertEqual(first, second)
        self.assertTrue(all(tool.deferred_constraints for tool in first))
        self.assertTrue(all(item.keyword for tool in first for item in tool.deferred_constraints))

    def test_projection_does_not_mutate_canonical_schema(self) -> None:
        source = canonical()
        before = deepcopy(source)
        project_hardware_tools(source)
        self.assertEqual(before, source)


if __name__ == "__main__":
    unittest.main()
