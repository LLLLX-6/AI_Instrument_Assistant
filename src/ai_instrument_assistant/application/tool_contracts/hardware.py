from __future__ import annotations

from typing import Any, overload

from ai_instrument_assistant.domain.artifacts import ArtifactReference, WaveformArtifact
from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.domain.measurement import (
    InstrumentStatus,
    MeasurementKind,
    MeasurementObservation,
    MeasurementResult,
)
from ai_instrument_assistant.domain.values import DutyCycle


_OPERATIONS = {
    MeasurementKind.FREQUENCY: "hardware.measure_frequency",
    MeasurementKind.VPP: "hardware.measure_vpp",
    MeasurementKind.WAVEFORM: "hardware.capture_waveform",
    MeasurementKind.PWM: "hardware.measure_pwm",
}


@overload
def mask_serial_number(serial_number: None) -> None: ...


@overload
def mask_serial_number(serial_number: str) -> str: ...


def mask_serial_number(serial_number: str | None) -> str | None:
    """Return the canonical public Hardware Tool representation of a serial number."""
    if serial_number is None:
        return None
    if serial_number == "***" or (
        len(serial_number) == 7 and serial_number.startswith("***")
    ):
        return serial_number
    if len(serial_number) <= 4:
        return "***"
    return f"***{serial_number[-4:]}"


def serialize_instrument_status(status: InstrumentStatus) -> dict[str, Any]:
    if not isinstance(status, InstrumentStatus):
        raise TypeError("status must be InstrumentStatus")
    return {
        "contract_version": "1.0",
        "operation": "hardware.get_status",
        "result": {
            "instrument": _identity(status.identity),
            "observed_at": status.observed_at.isoformat(),
        },
    }


def serialize_measurement_result(result: MeasurementResult) -> dict[str, Any]:
    if not isinstance(result, MeasurementResult):
        raise TypeError("result must be MeasurementResult")
    observations = {}
    for name in (
        "instrument_frequency", "instrument_vpp", "software_frequency",
        "software_period", "software_duty_cycle", "software_vpp",
        "software_mean", "software_rms",
    ):
        value = getattr(result, name)
        if value is not None:
            observations[name] = _observation(value)
    return {
        "contract_version": "1.0",
        "operation": _OPERATIONS[result.request.kind],
        "result": {
            "request_id": str(result.request.request_id),
            "kind": result.request.kind.value,
            "channel": result.request.channel,
            "context_id": result.request.context_id,
            "instrument": _identity(result.provenance.instrument_identity),
            "waveform": _waveform(result.waveform),
            "observations": observations,
            "quality": result.quality.value,
            "warnings": list(result.warnings),
            "coherence": {
                "software_observations": result.coherence.software_observations.value,
                "instrument_vs_software": result.coherence.instrument_vs_software.value,
            },
            "provenance": {
                "started_at": result.provenance.started_at.isoformat(),
                "completed_at": result.provenance.completed_at.isoformat(),
                "analysis_algorithm": None if result.provenance.analysis_algorithm_name is None else {
                    "name": result.provenance.analysis_algorithm_name,
                    "version": result.provenance.analysis_algorithm_version,
                },
            },
        },
    }


def _identity(identity: InstrumentIdentity) -> dict[str, str]:
    return {
        "manufacturer": identity.manufacturer,
        "model": identity.model,
        "serial_number": mask_serial_number(identity.serial_number),
        "firmware_version": identity.firmware_version,
    }


def _reference(reference: ArtifactReference) -> dict[str, Any]:
    value: dict[str, Any] = {
        "artifact_id": str(reference.artifact_id),
        "uri": reference.uri,
        "media_type": reference.media_type,
    }
    if reference.size_bytes is not None:
        value["size_bytes"] = reference.size_bytes
    if reference.sha256 is not None:
        value["sha256"] = reference.sha256
    return value


def _waveform(waveform: WaveformArtifact | None) -> dict[str, Any] | None:
    if waveform is None:
        return None
    return {
        "artifact": _reference(waveform.reference),
        "channel": waveform.channel,
        "point_count": waveform.point_count,
        "sample_interval_seconds": waveform.sample_interval_seconds,
        "time_range_seconds": [waveform.time_start_seconds, waveform.time_end_seconds],
        "voltage_range_v": [waveform.minimum_voltage, waveform.maximum_voltage],
        "acquisition_mode": waveform.acquisition_mode,
        "captured_at": waveform.captured_at.isoformat(),
    }


def _observation(observation: MeasurementObservation) -> dict[str, Any]:
    value: Any = observation.value
    if isinstance(value, DutyCycle):
        value = {"ratio": value.ratio, "percent": value.percent}
    return {
        "value": value,
        "source": observation.source.value,
        "method": observation.method,
        "observed_at": observation.observed_at.isoformat(),
        "quality": observation.quality.value,
        "warnings": list(observation.warnings),
        "evidence_artifact_ids": [
            str(identifier) for identifier in observation.evidence_artifact_ids
        ],
    }
