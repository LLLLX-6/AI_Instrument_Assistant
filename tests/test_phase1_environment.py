from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class PhaseOneEnvironmentTests(unittest.TestCase):
    def test_protocol_directory_skeleton_exists(self) -> None:
        protocol_root = REPOSITORY_ROOT / "protocols" / "jlceda" / "v1"

        self.assertTrue((protocol_root / "common").is_dir())
        self.assertTrue((protocol_root / "models").is_dir())
        self.assertTrue((protocol_root / "messages").is_dir())
        self.assertTrue((protocol_root / "operations").is_dir())
        self.assertTrue((protocol_root / "fixtures" / "valid").is_dir())
        self.assertTrue((protocol_root / "fixtures" / "invalid").is_dir())

    def test_fake_typescript_peer_is_reserved_for_test_support(self) -> None:
        extension_root = REPOSITORY_ROOT / "extensions" / "jlceda"

        self.assertTrue((extension_root / "tests" / "support").is_dir())
        self.assertFalse((extension_root / "src" / "fake").exists())

if __name__ == "__main__":
    unittest.main()
