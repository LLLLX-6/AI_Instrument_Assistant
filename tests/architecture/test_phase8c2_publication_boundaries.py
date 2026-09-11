from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PUBLICATION = ROOT / "src" / "ai_instrument_assistant" / "application" / "reasoning" / "publication"


class Phase8C2PublicationArchitectureTests(unittest.TestCase):
    def test_publication_core_has_no_external_runtime_dependencies(self) -> None:
        forbidden_roots = {
            "deepseek",
            "jlceda",
            "pyvisa",
            "websockets",
        }
        forbidden_fragments = (
            "integrations",
            "drivers",
            "communication",
            "hardware_tool_runtime",
            "physical_policy",
            "operation_scope",
        )
        for path in PUBLICATION.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            self.assertTrue(forbidden_roots.isdisjoint({name.split(".")[0] for name in imports}), path.name)
            self.assertFalse(any(fragment in name for name in imports for fragment in forbidden_fragments), path.name)

    def test_candidate_schema_has_no_execution_or_factual_fields(self) -> None:
        import json

        schema = json.loads(
            (ROOT / "protocols" / "teaching-claims" / "v1" / "structured-claim-candidate-set.schema.json")
            .read_text(encoding="utf-8")
        )
        fields = set(schema["properties"])
        forbidden = {
            "text", "value", "unit", "source", "diagnosis", "hypothesis",
            "tool", "action", "scope", "confirmation", "ipc", "waveform",
        }
        self.assertTrue(fields.isdisjoint(forbidden))

    def test_publication_objects_carry_no_execution_authority(self) -> None:
        from ai_instrument_assistant.application.reasoning.publication import (
            GroundedPublicationPlan,
            PublicationProjection,
            StructuredClaimCandidateSet,
        )

        names = {
            field.name
            for model in (PublicationProjection, StructuredClaimCandidateSet, GroundedPublicationPlan)
            for field in fields(model)
        }
        forbidden = {
            "tool", "tool_args", "operation", "scope", "confirmation",
            "ipc", "hardware_action", "eda_action", "visa_resource",
            "scpi", "waveform_samples", "source_code",
        }
        self.assertTrue(names.isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
