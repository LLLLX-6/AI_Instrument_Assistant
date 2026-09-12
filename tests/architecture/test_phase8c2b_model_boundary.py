from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class Phase8C2BArchitectureTests(unittest.TestCase):
    def test_application_port_has_no_provider_process_or_authority_surface(self) -> None:
        path = ROOT / "src/ai_instrument_assistant/application/reasoning/publication/model_runtime.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        source = path.read_text(encoding="utf-8")
        self.assertFalse(imports & {"subprocess", "json", "os"})
        for forbidden in ("deepseek", "DEEPSEEK_API_KEY", "executable_path", "tool_schema", "TrustedOperationScope"):
            self.assertNotIn(forbidden.lower(), source.lower())

    def test_executor_assembly_is_one_stream_call_and_zero_tool(self) -> None:
        root = ROOT / "extensions/deepseek-harness/src/model-candidate"
        sources = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.ts"))
        self.assertEqual(sources.count("ctx.llm.stream("), 1)
        self.assertIn("tools: []", sources)
        for forbidden in ("AgentLoop", "AgentRegistry", "ToolRuntime", "SessionStore", "Hardware", "JLCEDA"):
            self.assertNotIn(forbidden, sources)

    def test_private_request_schema_has_no_authority_or_execution_fields(self) -> None:
        path = ROOT / "protocols/harness-publication-bridge/v1/model-invocation-request.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(schema["properties"]), {"schema_id", "request_id", "request_digest", "prompt_profile", "projection"})
        encoded = json.dumps(schema)
        for forbidden in ("api_key", "authorization", "tool_schema", "executable", "timeout_expansion"):
            self.assertNotIn(forbidden, encoded.lower())


if __name__ == "__main__":
    unittest.main()
