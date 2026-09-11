from __future__ import annotations

import unittest

from validation.support.phase8b3.node_executor import NodeGovernedHardwareExecutor


class Backend:
    def __init__(self, *, start_error=False, stop_error=False) -> None:
        self.starts = 0
        self.stops = 0
        self.start_error = start_error
        self.stop_error = stop_error

    async def start(self):
        self.starts += 1
        if self.start_error:
            raise RuntimeError("start failed")

    async def stop(self):
        self.stops += 1
        if self.stop_error:
            raise RuntimeError("stop failed")


class Phase8B3NodeExecutorCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_child_success_closes_backend(self):
        backend = Backend()
        executor = NodeGovernedHardwareExecutor(
            backend_factory=lambda: backend,
            child_runner=lambda request, start: _start_then_return(
                start, {"status": "COMPLETED"}
            ),
        )
        result = await executor.execute({"request": "bounded"})
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual((backend.starts, backend.stops), (1, 1))

    async def test_node_launch_or_tool_failure_still_closes_backend(self):
        for failure in (RuntimeError("launch failed"), RuntimeError("tool failed")):
            with self.subTest(failure=str(failure)):
                backend = Backend()
                executor = NodeGovernedHardwareExecutor(
                    backend_factory=lambda: backend,
                    child_runner=lambda request, start, failure=failure: _start_then_raise(
                        start, failure
                    ),
                )
                with self.assertRaises(RuntimeError):
                    await executor.execute({"request": "bounded"})
                self.assertEqual((backend.starts, backend.stops), (1, 1))

    async def test_backend_start_failure_does_not_call_stop(self):
        backend = Backend(start_error=True)
        child_calls = 0

        async def child(request, start):
            nonlocal child_calls
            child_calls += 1
            await start()
            self.fail("child continued after backend start failure")

        with self.assertRaises(RuntimeError):
            await NodeGovernedHardwareExecutor(
                backend_factory=lambda: backend,
                child_runner=child,
            ).execute({})
        self.assertEqual((backend.starts, backend.stops, child_calls), (1, 0, 1))

    async def test_cleanup_failure_does_not_replace_primary_child_failure(self):
        backend = Backend(stop_error=True)
        primary_error = RuntimeError("primary child failure")
        executor = NodeGovernedHardwareExecutor(
            backend_factory=lambda: backend,
            child_runner=lambda request, start: _start_then_raise(start, primary_error),
        )

        with self.assertRaises(RuntimeError) as captured:
            await executor.execute({"request": "bounded"})

        self.assertIs(captured.exception, primary_error)
        self.assertEqual((backend.starts, backend.stops), (1, 1))

    async def test_cleanup_failure_after_success_is_bounded(self):
        backend = Backend(stop_error=True)
        executor = NodeGovernedHardwareExecutor(
            backend_factory=lambda: backend,
            child_runner=lambda request, start: _start_then_return(
                start, {"status": "COMPLETED"}
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError, "bounded hardware backend cleanup failure"
        ):
            await executor.execute({"request": "bounded"})
        self.assertEqual((backend.starts, backend.stops), (1, 1))

    async def test_child_preflight_rejection_never_starts_backend(self):
        backend = Backend()
        executor = NodeGovernedHardwareExecutor(
            backend_factory=lambda: backend,
            child_runner=lambda request, start: _return({"status": "FAILED"}),
        )

        result = await executor.execute({"request": "invalid-at-child-boundary"})

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual((backend.starts, backend.stops), (0, 0))


async def _return(value):
    return value


async def _raise(error):
    raise error


async def _start_then_return(start, value):
    await start()
    return value


async def _start_then_raise(start, error):
    await start()
    raise error


if __name__ == "__main__":
    unittest.main()
