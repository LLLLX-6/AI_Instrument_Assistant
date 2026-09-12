from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from .process_port import ManagedRuntime, OwnedChildContainment, OwnedRuntimeHandle, RuntimeKind


class RuntimeLifecycleError(RuntimeError):
    pass


class RuntimeStartupError(RuntimeLifecycleError):
    pass


class RuntimeRegistrationError(RuntimeLifecycleError):
    pass


class RuntimeStatus(StrEnum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    READY = "READY"
    CRASHED = "CRASHED"


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    kind: RuntimeKind
    status: RuntimeStatus


class LifecycleManager:
    """Owns bounded fake/real runtime handles without knowing subprocess details."""

    def __init__(self, *, containment: OwnedChildContainment) -> None:
        self._containment = containment
        self._runtimes: dict[RuntimeKind, ManagedRuntime] = {}
        self._handles: dict[RuntimeKind, OwnedRuntimeHandle] = {}
        self._statuses: dict[RuntimeKind, RuntimeStatus] = {}
        self._start_order: list[RuntimeKind] = []
        self._closed = False

    def register(self, runtime: ManagedRuntime) -> None:
        if runtime.kind in self._runtimes:
            raise RuntimeRegistrationError(f"runtime already registered: {runtime.kind.value}")
        self._runtimes[runtime.kind] = runtime
        self._statuses[runtime.kind] = RuntimeStatus.STOPPED

    def snapshot(self) -> tuple[RuntimeSnapshot, ...]:
        return tuple(RuntimeSnapshot(kind, self._statuses[kind]) for kind in self._runtimes)

    async def start(self, kind: RuntimeKind, timeout_seconds: float) -> OwnedRuntimeHandle:
        if self._closed:
            raise RuntimeLifecycleError("lifecycle manager is closed")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        existing = self._handles.get(kind)
        if existing is not None and existing.running:
            return existing
        try:
            runtime = self._runtimes[kind]
        except KeyError as error:
            raise RuntimeRegistrationError(f"runtime is not registered: {kind.value}") from error
        self._statuses[kind] = RuntimeStatus.STARTING
        handle: OwnedRuntimeHandle | None = None
        try:
            handle = await runtime.start()
            self._containment.attach(handle)
            self._handles[kind] = handle
            await asyncio.wait_for(handle.wait_ready(), timeout=timeout_seconds)
        except asyncio.CancelledError:
            if handle is not None:
                try:
                    await handle.stop()
                finally:
                    self._containment.release(handle)
                    self._handles.pop(kind, None)
            self._statuses[kind] = RuntimeStatus.STOPPED
            raise
        except Exception as error:
            if handle is not None:
                try:
                    await handle.stop()
                finally:
                    self._containment.release(handle)
                    self._handles.pop(kind, None)
            self._statuses[kind] = RuntimeStatus.STOPPED
            raise RuntimeStartupError(f"runtime failed to become ready: {kind.value}") from error
        self._statuses[kind] = RuntimeStatus.READY
        if kind not in self._start_order:
            self._start_order.append(kind)
        return handle

    def observe_crash(self, kind: RuntimeKind) -> None:
        if kind in self._handles:
            self._statuses[kind] = RuntimeStatus.CRASHED

    async def stop(self, kind: RuntimeKind) -> None:
        handle = self._handles.pop(kind, None)
        if handle is None:
            self._statuses[kind] = RuntimeStatus.STOPPED
            return
        try:
            await handle.stop()
        finally:
            self._containment.release(handle)
            self._statuses[kind] = RuntimeStatus.STOPPED
            if kind in self._start_order:
                self._start_order.remove(kind)

    async def shutdown(self) -> None:
        if self._closed:
            return
        for kind in tuple(reversed(self._start_order)):
            await self.stop(kind)
        self._containment.close()
        self._closed = True
