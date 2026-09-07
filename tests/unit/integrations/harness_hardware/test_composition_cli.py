from __future__ import annotations

import unittest

from ai_instrument_assistant.bootstrap.hardware_tool import HardwareBackend
from ai_instrument_assistant.integrations.harness_hardware.cli import parse_args
from ai_instrument_assistant.integrations.harness_hardware.composition import (
    build_harness_hardware_backend,
)


class HarnessHardwareCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_fake_composition_uses_actual_runtime_and_explicit_lifecycle(self) -> None:
        backend = build_harness_hardware_backend(
            HardwareBackend.FAKE, secret_loader=lambda: bytes(range(32)), port=0
        )
        await backend.start()
        try:
            self.assertEqual("fake", backend.backend.value)
            self.assertTrue(backend.server.uri.startswith("ws://127.0.0.1:"))
        finally:
            await backend.stop()

    def test_cli_rejects_non_loopback_host_and_requires_real_resource(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["--backend", "fake", "--host", "0.0.0.0"])
        with self.assertRaises(SystemExit):
            parse_args(["--backend", "real"])
        parsed = parse_args(["--backend", "fake", "--port", "49625"])
        self.assertEqual("127.0.0.1", parsed.host)
        self.assertFalse(parsed.initialize_secret)


if __name__ == "__main__":
    unittest.main()
