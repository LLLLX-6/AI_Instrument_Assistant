from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "protocols/harness-hardware/v1/compatibility/harness-api.fixture.json"


class HarnessVersionFreezeTests(unittest.TestCase):
    def test_reviewed_harness_api_shape_is_pinned_exactly(self) -> None:
        value = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual("d347e703908d0406b7a7ef80e3a0e594d86b2215", value["reviewed_git_commit"])
        self.assertEqual("dsh@0.1.3-alpha.1", value["reviewed_source_version"])
        self.assertEqual("aia-harness-hardware/v1", value["adapter_contract"])
        self.assertEqual("exact-reviewed-shape-only", value["compatibility_policy"])
        self.assertIsNone(value["compatible_range"]["minimum"])
        self.assertIsNone(value["compatible_range"]["maximum"])

    def test_observed_registry_version_is_not_claimed_compatible(self) -> None:
        value = json.loads(FIXTURE.read_text(encoding="utf-8"))
        observed = value["observed_registry_packages"]
        self.assertEqual("0.1.2-rc.1", observed["@deepseek-ai/dsh"])
        self.assertNotIn("0.1.2-rc.1", value["verified_compatible_versions"])
        self.assertEqual(
            ["inject", "apply", "ctx.tools.register", "defineTool", "async execute", "AbortSignal"],
            value["reviewed_api_shape"],
        )


if __name__ == "__main__":
    unittest.main()
