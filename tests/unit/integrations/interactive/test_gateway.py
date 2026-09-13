from __future__ import annotations

import unittest

from ai_instrument_assistant.integrations.interactive import LoopbackGatewayConfig


class InteractiveGatewayConfigTests(unittest.TestCase):
    def test_default_uses_reviewed_separate_interactive_listener(self) -> None:
        config = LoopbackGatewayConfig()
        self.assertEqual(config.bind_host, "127.0.0.1")
        self.assertEqual(config.port, 49626)

    def test_non_loopback_or_invalid_path_fails_closed(self) -> None:
        for values in (
            {"bind_host": "0.0.0.0"},
            {"bind_host": "localhost"},
            {"port": 0},
            {"port": 49624},
            {"port": 49625},
        ):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    LoopbackGatewayConfig(**values)


if __name__ == "__main__":
    unittest.main()
