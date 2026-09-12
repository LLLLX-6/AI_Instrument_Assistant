from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class RuntimeKind(StrEnum):
    JLCEDA_GATEWAY = "JLCEDA_GATEWAY"
    INTERACTIVE_GATEWAY = "INTERACTIVE_GATEWAY"
    HARDWARE_BACKEND = "HARDWARE_BACKEND"
    VISA_SESSION = "VISA_SESSION"
    DEEPSEEK_EXECUTOR = "DEEPSEEK_EXECUTOR"
    FINAL_EGRESS_EXECUTOR = "FINAL_EGRESS_EXECUTOR"


class RuntimeLifetime(StrEnum):
    HOST_LIFETIME = "HOST_LIFETIME"
    ON_DEMAND = "ON_DEMAND"
    ONE_ATTEMPT = "ONE_ATTEMPT"


def intended_lifetime(kind: RuntimeKind) -> RuntimeLifetime:
    if kind in {RuntimeKind.JLCEDA_GATEWAY, RuntimeKind.INTERACTIVE_GATEWAY}:
        return RuntimeLifetime.HOST_LIFETIME
    if kind is RuntimeKind.HARDWARE_BACKEND:
        return RuntimeLifetime.ON_DEMAND
    return RuntimeLifetime.ONE_ATTEMPT


class OwnedRuntimeHandle(Protocol):
    """Explicit owned-child handle; it makes no POSIX signal assumptions."""

    @property
    def kind(self) -> RuntimeKind: ...

    @property
    def running(self) -> bool: ...

    async def wait_ready(self) -> None: ...

    async def stop(self) -> None: ...


class ManagedRuntime(Protocol):
    @property
    def kind(self) -> RuntimeKind: ...

    async def start(self) -> OwnedRuntimeHandle: ...


class OwnedChildContainment(Protocol):
    """Production seam for a Windows Job Object or equivalent owned handle."""

    def attach(self, handle: OwnedRuntimeHandle) -> None: ...
    def release(self, handle: OwnedRuntimeHandle) -> None: ...
    def close(self) -> None: ...
