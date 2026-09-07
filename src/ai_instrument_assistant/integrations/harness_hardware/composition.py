from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ai_instrument_assistant.bootstrap.hardware_tool import (
    HardwareBackend,
    HardwareToolComposition,
    build_hardware_tool_composition,
)

from .server import BackendServerConfig, HarnessHardwareServer


@dataclass(slots=True)
class HarnessHardwareBackend:
    composition: HardwareToolComposition
    server: HarnessHardwareServer
    backend: HardwareBackend
    _started: bool = False

    async def start(self) -> None:
        if self._started:
            raise RuntimeError("Harness Hardware backend is already running")
        self.composition.connect()
        try:
            await self.server.start()
        except Exception:
            self.composition.close()
            raise
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self.server.stop()
        finally:
            self.composition.close()
            self._started = False


def build_harness_hardware_backend(
    backend: HardwareBackend,
    *,
    secret_loader: Callable[[], bytes],
    port: int = 49_625,
    resource_name: str | None = None,
    timeout_seconds: float = 5.0,
    visa_backend: str | None = None,
) -> HarnessHardwareBackend:
    composition = build_hardware_tool_composition(
        backend,
        resource_name=resource_name,
        timeout_seconds=timeout_seconds,
        visa_backend=visa_backend,
    )
    server = HarnessHardwareServer(
        runtime=composition.runtime,
        secret_loader=secret_loader,
        config=BackendServerConfig(port=port),
    )
    return HarnessHardwareBackend(composition, server, backend)
