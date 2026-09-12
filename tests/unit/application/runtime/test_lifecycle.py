from __future__ import annotations

import asyncio
import unittest

from ai_instrument_assistant.application.runtime import (
    LifecycleManager,
    RuntimeKind,
    RuntimeStartupError,
    RuntimeLifetime,
    intended_lifetime,
)
from tests.support.interactive_fakes import FakeContainment, FakeManagedRuntime


class LifecycleManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_and_reverse_shutdown_order(self) -> None:
        log: list[str] = []
        containment = FakeContainment(log)
        manager = LifecycleManager(containment=containment)
        gateway = FakeManagedRuntime(RuntimeKind.JLCEDA_GATEWAY, log)
        interactive = FakeManagedRuntime(RuntimeKind.INTERACTIVE_GATEWAY, log)
        manager.register(gateway)
        manager.register(interactive)
        await manager.start(RuntimeKind.JLCEDA_GATEWAY, timeout_seconds=1)
        await manager.start(RuntimeKind.INTERACTIVE_GATEWAY, timeout_seconds=1)
        await manager.shutdown()
        self.assertLess(log.index("stop:INTERACTIVE_GATEWAY"), log.index("stop:JLCEDA_GATEWAY"))
        self.assertEqual(containment.attached, set())

    async def test_startup_timeout_cleans_up(self) -> None:
        log: list[str] = []
        runtime = FakeManagedRuntime(RuntimeKind.HARDWARE_BACKEND, log, ready=False)
        manager = LifecycleManager(containment=FakeContainment(log))
        manager.register(runtime)
        with self.assertRaises(RuntimeStartupError):
            await manager.start(RuntimeKind.HARDWARE_BACKEND, timeout_seconds=0.01)
        self.assertIn("stop:HARDWARE_BACKEND", log)

    async def test_cancelled_startup_cleans_up_owned_child(self) -> None:
        log: list[str] = []
        containment = FakeContainment(log)
        runtime = FakeManagedRuntime(RuntimeKind.HARDWARE_BACKEND, log, ready=False)
        manager = LifecycleManager(containment=containment)
        manager.register(runtime)
        task = asyncio.create_task(
            manager.start(RuntimeKind.HARDWARE_BACKEND, timeout_seconds=10)
        )
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(containment.attached, set())
        self.assertIn("stop:HARDWARE_BACKEND", log)

    async def test_crash_and_stop_are_idempotently_contained(self) -> None:
        log: list[str] = []
        runtime = FakeManagedRuntime(RuntimeKind.HARDWARE_BACKEND, log)
        manager = LifecycleManager(containment=FakeContainment(log))
        manager.register(runtime)
        await manager.start(RuntimeKind.HARDWARE_BACKEND, 1)
        runtime.crash()
        manager.observe_crash(RuntimeKind.HARDWARE_BACKEND)
        await manager.stop(RuntimeKind.HARDWARE_BACKEND)
        await manager.stop(RuntimeKind.HARDWARE_BACKEND)
        self.assertEqual(log.count("stop:HARDWARE_BACKEND"), 1)

    async def test_intended_lifetimes_keep_sensitive_runtimes_on_demand(self) -> None:
        self.assertEqual(intended_lifetime(RuntimeKind.JLCEDA_GATEWAY), RuntimeLifetime.HOST_LIFETIME)
        self.assertEqual(intended_lifetime(RuntimeKind.INTERACTIVE_GATEWAY), RuntimeLifetime.HOST_LIFETIME)
        self.assertEqual(intended_lifetime(RuntimeKind.HARDWARE_BACKEND), RuntimeLifetime.ON_DEMAND)
        self.assertEqual(intended_lifetime(RuntimeKind.VISA_SESSION), RuntimeLifetime.ONE_ATTEMPT)
        self.assertEqual(intended_lifetime(RuntimeKind.DEEPSEEK_EXECUTOR), RuntimeLifetime.ONE_ATTEMPT)
        self.assertEqual(intended_lifetime(RuntimeKind.FINAL_EGRESS_EXECUTOR), RuntimeLifetime.ONE_ATTEMPT)


if __name__ == "__main__":
    unittest.main()
