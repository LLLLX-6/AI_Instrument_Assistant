from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class BootstrapOutcome(StrEnum):
    STARTED = "STARTED"
    EXISTING_COMPATIBLE = "EXISTING_COMPATIBLE"
    VERSION_INCOMPATIBLE = "VERSION_INCOMPATIBLE"
    LOCAL_PORT_IN_USE = "LOCAL_PORT_IN_USE"


class SingleInstancePort(Protocol):
    """Platform adapter seam for a Windows named object or equivalent."""

    def acquire(self) -> str: ...
    def release(self) -> None: ...


class HostRunnerPort(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class ApplicationBootstrap:
    """Non-CLI product bootstrap service; UI packaging is deferred."""

    def __init__(self, single_instance: SingleInstancePort, runner: HostRunnerPort) -> None:
        self._single_instance = single_instance
        self._runner = runner
        self._started = False

    async def start(self) -> BootstrapOutcome:
        result = self._single_instance.acquire()
        if result == "EXISTING_COMPATIBLE":
            return BootstrapOutcome.EXISTING_COMPATIBLE
        if result == "INCOMPATIBLE":
            return BootstrapOutcome.VERSION_INCOMPATIBLE
        if result == "PORT_IN_USE":
            return BootstrapOutcome.LOCAL_PORT_IN_USE
        if result != "ACQUIRED":
            return BootstrapOutcome.LOCAL_PORT_IN_USE
        try:
            await self._runner.start()
        except BaseException:
            self._single_instance.release()
            raise
        self._started = True
        return BootstrapOutcome.STARTED

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self._runner.stop()
        finally:
            self._single_instance.release()
            self._started = False
