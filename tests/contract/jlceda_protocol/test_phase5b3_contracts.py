from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class PhaseFiveBThreeContractTests(unittest.TestCase):
    def test_selection_operation_schema_exists(self) -> None:
        self.assertTrue(
            (ROOT / "protocols/jlceda/v1/messages/eda-selection.schema.json").is_file()
        )


if __name__ == "__main__":
    unittest.main()
