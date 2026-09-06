from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_instrument_assistant.adapters.artifacts import InMemoryArtifactStore
from ai_instrument_assistant.adapters.instruments import SimulatedOscilloscope
from ai_instrument_assistant.analysis import DeterministicWaveformAnalysisEngine
from ai_instrument_assistant.application.services import MeasurementService
from ai_instrument_assistant.application.tool_runtime import HardwareToolRuntime
from ai_instrument_assistant.communication.visa import VisaTransport
from ai_instrument_assistant.domain.measurement import ObservationSource
from ai_instrument_assistant.protocol.hardware import HardwareToolContractValidator

from .hardware import MeasurementRuntime, build_ds1102ze_measurement_runtime


class HardwareBackend(StrEnum):
    REAL = "real"
    FAKE = "fake"


@dataclass(slots=True)
class HardwareToolComposition:
    """Own the runtime and its explicitly selected backend lifecycle."""

    runtime: HardwareToolRuntime
    measurement_runtime: MeasurementRuntime
    backend: HardwareBackend

    def connect(self) -> None:
        self.measurement_runtime.connect()

    def close(self) -> None:
        self.measurement_runtime.close()

    def __enter__(self) -> HardwareToolComposition:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def build_fake_hardware_tool_composition() -> HardwareToolComposition:
    oscilloscope = SimulatedOscilloscope()
    artifact_store = InMemoryArtifactStore()
    service = MeasurementService(
        oscilloscope=oscilloscope,
        analyzer=DeterministicWaveformAnalysisEngine(),
        artifact_store=artifact_store,
        instrument_observation_source=ObservationSource.SIMULATED,
    )
    measurement_runtime = MeasurementRuntime(service, artifact_store, oscilloscope)
    return HardwareToolComposition(
        runtime=HardwareToolRuntime(service, HardwareToolContractValidator()),
        measurement_runtime=measurement_runtime,
        backend=HardwareBackend.FAKE,
    )


def build_real_hardware_tool_composition(
    resource_name: str,
    *,
    timeout_seconds: float = 5.0,
    visa_backend: str | None = None,
    transport: VisaTransport | None = None,
) -> HardwareToolComposition:
    measurement_runtime = build_ds1102ze_measurement_runtime(
        resource_name,
        timeout_seconds=timeout_seconds,
        backend=visa_backend,
        transport=transport,
    )
    return HardwareToolComposition(
        runtime=HardwareToolRuntime(
            measurement_runtime.service,
            HardwareToolContractValidator(),
        ),
        measurement_runtime=measurement_runtime,
        backend=HardwareBackend.REAL,
    )


def build_hardware_tool_composition(
    backend: HardwareBackend,
    *,
    resource_name: str | None = None,
    timeout_seconds: float = 5.0,
    visa_backend: str | None = None,
    transport: VisaTransport | None = None,
) -> HardwareToolComposition:
    if not isinstance(backend, HardwareBackend):
        raise TypeError("backend must be HardwareBackend")
    if backend is HardwareBackend.FAKE:
        return build_fake_hardware_tool_composition()
    if resource_name is None or not resource_name.strip():
        raise ValueError("resource_name is required for the real backend")
    return build_real_hardware_tool_composition(
        resource_name,
        timeout_seconds=timeout_seconds,
        visa_backend=visa_backend,
        transport=transport,
    )
