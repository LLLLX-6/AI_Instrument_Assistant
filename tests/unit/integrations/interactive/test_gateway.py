from __future__ import annotations

import unittest

from ai_instrument_assistant.integrations.interactive import LoopbackGatewayConfig


class InteractiveGatewayConfigTests(unittest.TestCase):
    def test_default_reuses_existing_host_port_with_versioned_path(self) -> None:
        config = LoopbackGatewayConfig()
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 49624)
        self.assertEqual(config.path, "/interactive/v1")

    def test_non_loopback_or_invalid_path_fails_closed(self) -> None:
        for values in (
            {"host": "0.0.0.0"},
            {"host": "localhost"},
            {"port": 0},
            {"path": "/"},
        ):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    LoopbackGatewayConfig(**values)


if __name__ == "__main__":
    unittest.main()
