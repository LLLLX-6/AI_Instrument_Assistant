from __future__ import annotations

from dataclasses import dataclass

from ai_instrument_assistant.adapters.artifacts import InMemoryArtifactStore
from ai_instrument_assistant.analysis import DeterministicWaveformAnalysisEngine
from ai_instrument_assistant.application.ports.artifact_store import ArtifactStore
from ai_instrument_assistant.application.ports.oscilloscope import OscilloscopeInterface
from ai_instrument_assistant.application.services import MeasurementService
from ai_instrument_assistant.communication.visa import VisaTransport
from ai_instrument_assistant.drivers.rigol import DS1102ZEDriver
from ai_instrument_assistant.integrations.visa import PyVisaTransport


@dataclass(slots=True)
class MeasurementRuntime:
    """Own one connected oscilloscope and its application-level service graph."""

    service: MeasurementService
    artifact_store: ArtifactStore
    _oscilloscope: OscilloscopeInterface
    _connected: bool = False

    def connect(self) -> None:
        if self._connected:
            return
        self._oscilloscope.connect()
        self._connected = True

    def close(self) -> None:
        if not self._connected:
            return
        self._connected = False
        self._oscilloscope.disconnect()

    def __enter__(self) -> MeasurementRuntime:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def build_ds1102ze_measurement_runtime(
    resource_name: str,
    *,
    timeout_seconds: float = 5.0,
    backend: str | None = None,
    transport: VisaTransport | None = None,
    artifact_store: ArtifactStore | None = None,
) -> MeasurementRuntime:
    """Wire the reviewed concrete DS1102Z-E graph without a DI framework."""

    resolved_transport = (
        transport if transport is not None else PyVisaTransport(backend=backend)
    )
    resolved_store = (
        artifact_store if artifact_store is not None else InMemoryArtifactStore()
    )
    oscilloscope = DS1102ZEDriver(
        resolved_transport,
        resource_name,
        timeout_seconds=timeout_seconds,
    )
    service = MeasurementService(
        oscilloscope=oscilloscope,
        analyzer=DeterministicWaveformAnalysisEngine(),
        artifact_store=resolved_store,
    )
    return MeasurementRuntime(service, resolved_store, oscilloscope)


def discover_visa_resources(*, backend: str | None = None) -> tuple[str, ...]:
    """Configuration-time discovery kept outside the application service."""

    return PyVisaTransport(backend=backend).discover_resources()
