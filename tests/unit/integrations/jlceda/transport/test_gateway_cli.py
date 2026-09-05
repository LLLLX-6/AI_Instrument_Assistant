from __future__ import annotations

import argparse
import unittest
from unittest.mock import patch

from scripts.run_jlceda_gateway import parse_args, stable_port


class GatewayCliConfigurationTests(unittest.TestCase):
    def test_default_endpoint_uses_stable_project_port(self) -> None:
        with patch("sys.argv", ["run_jlceda_gateway.py"]):
            self.assertEqual(49624, parse_args().port)

    def test_explicit_stable_port_is_supported(self) -> None:
        self.assertEqual(49625, stable_port("49625"))

    def test_ephemeral_port_is_rejected_for_production_cli(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            stable_port("0")


if __name__ == "__main__":
    unittest.main()
