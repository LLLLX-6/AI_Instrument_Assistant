from __future__ import annotations

import unittest

from ai_instrument_assistant.bootstrap.application_host import (
    ApplicationBootstrap,
    BootstrapOutcome,
)
from tests.support.interactive_fakes import FakeHostRunner, FakeSingleInstance


class ApplicationBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_second_compatible_launcher_reuses_existing_host(self) -> None:
        runner = FakeHostRunner()
        bootstrap = ApplicationBootstrap(FakeSingleInstance("EXISTING_COMPATIBLE"), runner)
        result = await bootstrap.start()
        self.assertEqual(result, BootstrapOutcome.EXISTING_COMPATIBLE)
        self.assertEqual(runner.starts, 0)

    async def test_incompatible_or_port_collision_never_kills_unknown_process(self) -> None:
        for result in ("INCOMPATIBLE", "PORT_IN_USE"):
            with self.subTest(result=result):
                single = FakeSingleInstance(result)
                runner = FakeHostRunner()
                bootstrap = ApplicationBootstrap(single, runner)
                outcome = await bootstrap.start()
                self.assertIn(outcome, {BootstrapOutcome.VERSION_INCOMPATIBLE, BootstrapOutcome.LOCAL_PORT_IN_USE})
                self.assertEqual(runner.starts, 0)
                self.assertEqual(single.terminate_calls, 0)

    async def test_failed_host_start_releases_owned_single_instance_claim(self) -> None:
        single = FakeSingleInstance("ACQUIRED")
        bootstrap = ApplicationBootstrap(single, FakeHostRunner(fail_start=True))
        with self.assertRaises(RuntimeError):
            await bootstrap.start()
        self.assertEqual(single.release_calls, 1)
        self.assertEqual(single.terminate_calls, 0)


if __name__ == "__main__":
    unittest.main()
