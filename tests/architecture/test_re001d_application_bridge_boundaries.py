from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class RE001DApplicationBridgeBoundaryTests(unittest.TestCase):
    def test_private_schema_cannot_serialize_authority_or_credentials(self):
        text = "\n".join(
            item.read_text(encoding="utf-8")
            for item in (ROOT / "protocols/re001d-application/v1").glob("*.json")
        ).lower()
        for forbidden in (
            "trustedoperationscope", "probesetupconfirmation", "authorization_token",
            "capability_handle", "hardware_psk", "secret_file",
        ):
            self.assertNotIn(forbidden, text)
        production = (ROOT / "src/ai_instrument_assistant/application/services/re001d_lite.py").read_text(encoding="utf-8")
        self.assertNotIn("validation.support", production)

    def test_python_bridge_has_no_hardware_transport_or_authority_dependency(self):
        text = "\n".join(
            item.read_text(encoding="utf-8")
            for item in (ROOT / "src/ai_instrument_assistant/integrations/re001d_application").glob("*.py")
        ).lower()
        for forbidden in (
            "harness_hardware", "trustedoperationscope", "probesetupconfirmation",
            "pyvisa", "scpi", "49625", "hardwaretoolruntime",
        ):
            self.assertNotIn(forbidden, text)

    def test_typescript_bridge_does_not_duplicate_analysis_or_spawn_python(self):
        root = ROOT / "extensions/deepseek-harness/src"
        text = (root / "re001d-application-client.ts").read_text(encoding="utf-8") + (
            root / "interactive-re001d-authority.ts"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "child_process", "RCSinglePointMeasurementAnalyzer", "gain_ratio",
            "gain_db", "frequency_relative_deviation", "python.exe",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
