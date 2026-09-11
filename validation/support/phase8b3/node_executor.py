from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol


MAX_PRIVATE_MESSAGE_BYTES = 65_536


class HardwareBackendLifecycle(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


BackendStarter = Callable[[], Awaitable[None]]
ChildRunner = Callable[
    [Mapping[str, Any], BackendStarter], Awaitable[Mapping[str, Any]]
]


class NodeGovernedHardwareExecutor:
    """Validation adapter: backend lifecycle + one-shot bounded Node governance."""

    def __init__(
        self,
        *,
        backend_factory: Callable[[], HardwareBackendLifecycle],
        child_runner: ChildRunner,
    ) -> None:
        self._backend_factory = backend_factory
        self._child_runner = child_runner

    async def execute(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        backend = self._backend_factory()
        started = False
        result: Mapping[str, Any] | None = None
        primary_error: BaseException | None = None

        async def start_backend() -> None:
            nonlocal started
            if started:
                return
            await backend.start()
            started = True

        try:
            result = await self._child_runner(request, start_backend)
        except BaseException as error:
            primary_error = error
        finally:
            if started:
                try:
                    await backend.stop()
                except BaseException as cleanup_error:
                    if primary_error is None:
                        raise RuntimeError("bounded hardware backend cleanup failure") from cleanup_error
        if primary_error is not None:
            raise primary_error
        if result is None:
            raise RuntimeError("bounded hardware executor completed without a receipt")
        return result


def inherited_stdio_child_runner(
    *, repository_root: Path, timeout_seconds: float = 45.0
) -> ChildRunner:
    script = (
        repository_root
        / "extensions"
        / "deepseek-harness"
        / "scripts"
        / "execute-phase8b3-governed-hardware.mjs"
    )

    async def run(
        request: Mapping[str, Any], start_backend: BackendStarter
    ) -> Mapping[str, Any]:
        encoded = json.dumps(request, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        if len(encoded) > MAX_PRIVATE_MESSAGE_BYTES:
            raise ValueError("private validation request exceeds bounded size")
        process = await asyncio.create_subprocess_exec(
            "node",
            str(script),
            cwd=str(repository_root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=dict(os.environ),
        )
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("bounded Node executor stdio was not created")
        try:
            async with asyncio.timeout(timeout_seconds):
                process.stdin.write(encoded + b"\n")
                await process.stdin.drain()
                first = await _read_bounded_line(process.stdout)
                first_value = _decode_object(first)
                if first_value == {
                    "contract": "aia-phase8b3-validation",
                    "contract_version": "1.0",
                    "kind": "backend_start_required",
                }:
                    await start_backend()
                    ready = {
                        "contract": "aia-phase8b3-validation",
                        "contract_version": "1.0",
                        "kind": "backend_ready",
                    }
                    process.stdin.write(
                        json.dumps(ready, separators=(",", ":")).encode("utf-8") + b"\n"
                    )
                    await process.stdin.drain()
                    stdout = await _read_bounded_line(process.stdout)
                else:
                    stdout = first
                process.stdin.close()
                await process.wait()
                trailing = await process.stdout.read(MAX_PRIVATE_MESSAGE_BYTES + 1)
                if trailing.strip():
                    raise ValueError("bounded Node executor returned extra output")
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        return _decode_object(stdout)

    return run


async def _read_bounded_line(reader: asyncio.StreamReader) -> bytes:
    value = await reader.readline()
    if not value or len(value) > MAX_PRIVATE_MESSAGE_BYTES:
        raise ValueError("private validation stdio line is missing or exceeds bounded size")
    return value


def _decode_object(value: bytes) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("bounded Node executor returned invalid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("bounded Node executor message must be an object")
    return decoded
