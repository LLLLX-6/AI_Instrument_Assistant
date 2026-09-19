from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from ai_instrument_assistant.domain.artifacts import ArtifactReference, WaveformArtifact
from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.domain.measurement import (
    CoherenceKind,
    MeasurementCoherence,
    MeasurementKind,
    MeasurementObservation,
    MeasurementProvenance,
    MeasurementQuality,
    MeasurementRequest,
    MeasurementResult,
    ObservationQuality,
    ObservationSource,
)
from ai_instrument_assistant.protocol.hardware import HardwareToolContractValidator


_BINDINGS = {
    "hardware.measure_frequency": (MeasurementKind.FREQUENCY, "instrument_frequency"),
    "hardware.measure_vpp": (MeasurementKind.VPP, "instrument_vpp"),
}

# A frequency/Vpp measurement observation may carry real instrument provenance
# or honestly labelled simulated-backend provenance; both stay distinct. The
# wire schema additionally admits "software_analysis", which is not a valid
# provenance for a measurement observation and must fail closed here.
_MEASUREMENT_OBSERVATION_SOURCES = frozenset({
    ObservationSource.INSTRUMENT,
    ObservationSource.SIMULATED,
})


class CanonicalMeasurementMappingError(ValueError):
    """Bounded rejection at the canonical Hardware/domain boundary."""


@dataclass(frozen=True, slots=True)
class CanonicalMeasurementFailure:
    """A canonical operation failure, distinct from a transport exception."""

    operation: str
    channel: int
    error_code: str
    quality: MeasurementQuality = MeasurementQuality.FAILED
    observation_quality: ObservationQuality = ObservationQuality.UNAVAILABLE


class CanonicalMeasurementResultMapper:
    """Strictly map only frequency/Vpp canonical successes into domain evidence."""

    def __init__(self, validator: HardwareToolContractValidator | None = None) -> None:
        self._validator = validator or HardwareToolContractValidator()

    def map_success(
        self,
        payload: Any,
        *,
        expected_operation: str,
        expected_channel: int,
    ) -> MeasurementResult:
        value = self._validated(payload)
        self._expected(expected_operation, expected_channel)
        if value.get("ok") is not True:
            raise CanonicalMeasurementMappingError("canonical_result_not_successful")
        if value.get("operation") != expected_operation:
            raise CanonicalMeasurementMappingError("operation_binding_mismatch")
        kind, observation_field = _BINDINGS[expected_operation]
        result = _object(value.get("result"))
        if result.get("kind") != kind.value:
            raise CanonicalMeasurementMappingError("measurement_kind_mismatch")
        if result.get("channel") != expected_channel:
            raise CanonicalMeasurementMappingError("channel_binding_mismatch")

        observations = _object(result.get("observations"))
        if set(observations) != {observation_field}:
            raise CanonicalMeasurementMappingError("measurement_observation_mismatch")
        observation = self._observation(_object(observations[observation_field]), kind)
        request = MeasurementRequest(
            request_id=_uuid(result.get("request_id")),
            kind=kind,
            channel=expected_channel,
            context_id=_optional_text(result.get("context_id")),
        )
        provenance_wire = _object(result.get("provenance"))
        algorithm = provenance_wire.get("analysis_algorithm")
        if algorithm is not None:
            raise CanonicalMeasurementMappingError("instrument_metric_cannot_claim_analysis_algorithm")
        provenance = MeasurementProvenance(
            instrument_identity=self._identity(_object(result.get("instrument"))),
            channel=expected_channel,
            started_at=_timestamp(provenance_wire.get("started_at")),
            completed_at=_timestamp(provenance_wire.get("completed_at")),
        )
        coherence_wire = _object(result.get("coherence"))
        waveform = self._waveform(result.get("waveform"), expected_channel)
        fields = {observation_field: observation}
        return MeasurementResult(
            request=request,
            waveform=waveform,
            quality=MeasurementQuality(result.get("quality")),
            warnings=tuple(_strings(result.get("warnings"))),
            coherence=MeasurementCoherence(
                CoherenceKind(coherence_wire.get("software_observations")),
                CoherenceKind(coherence_wire.get("instrument_vs_software")),
            ),
            provenance=provenance,
            **fields,
        )

    def map_failure(
        self,
        payload: Any,
        *,
        expected_operation: str,
        expected_channel: int,
    ) -> CanonicalMeasurementFailure:
        value = self._validated(payload)
        self._expected(expected_operation, expected_channel)
        if value.get("ok") is not False:
            raise CanonicalMeasurementMappingError("canonical_result_not_failure")
        if value.get("operation") != expected_operation:
            raise CanonicalMeasurementMappingError("operation_binding_mismatch")
        error = _object(value.get("error"))
        return CanonicalMeasurementFailure(
            operation=expected_operation,
            channel=expected_channel,
            error_code=_text(error.get("code")),
        )

    def _validated(self, payload: Any) -> Mapping[str, Any]:
        try:
            self._validator.validate_runtime_response(payload)
        except Exception as error:
            raise CanonicalMeasurementMappingError("canonical_schema_invalid") from error
        return _object(payload)

    @staticmethod
    def _expected(operation: str, channel: int) -> None:
        if operation not in _BINDINGS:
            raise CanonicalMeasurementMappingError("operation_not_supported")
        if channel not in (1, 2) or isinstance(channel, bool):
            raise CanonicalMeasurementMappingError("channel_not_supported")

    @staticmethod
    def _identity(value: Mapping[str, Any]) -> InstrumentIdentity:
        try:
            return InstrumentIdentity(
                manufacturer=_text(value.get("manufacturer")),
                model=_text(value.get("model")),
                serial_number=_text(value.get("serial_number")),
                firmware_version=_text(value.get("firmware_version")),
            )
        except (TypeError, ValueError) as error:
            raise CanonicalMeasurementMappingError("instrument_identity_invalid") from error

    @staticmethod
    def _observation(value: Mapping[str, Any], kind: MeasurementKind) -> MeasurementObservation:
        try:
            source = ObservationSource(value.get("source"))
        except ValueError as error:
            raise CanonicalMeasurementMappingError("observation_source_invalid") from error
        if source not in _MEASUREMENT_OBSERVATION_SOURCES:
            raise CanonicalMeasurementMappingError("observation_source_invalid")
        numeric = value.get("value")
        if isinstance(numeric, bool) or not isinstance(numeric, (int, float)) or not math.isfinite(float(numeric)):
            raise CanonicalMeasurementMappingError("observation_value_invalid")
        number = float(numeric)
        if kind is MeasurementKind.FREQUENCY and number <= 0:
            raise CanonicalMeasurementMappingError("frequency_not_positive")
        if kind is MeasurementKind.VPP and number < 0:
            raise CanonicalMeasurementMappingError("vpp_negative")
        try:
            return MeasurementObservation(
                value=number,
                source=source,
                method=_text(value.get("method")),
                observed_at=_timestamp(value.get("observed_at")),
                quality=ObservationQuality(value.get("quality")),
                warnings=tuple(_strings(value.get("warnings"))),
                evidence_artifact_ids=tuple(_uuid(item) for item in _list(value.get("evidence_artifact_ids"))),
            )
        except (TypeError, ValueError) as error:
            raise CanonicalMeasurementMappingError("observation_invalid") from error

    @staticmethod
    def _waveform(value: Any, expected_channel: int) -> WaveformArtifact | None:
        if value is None:
            return None
        waveform = _object(value)
        if waveform.get("channel") != expected_channel:
            raise CanonicalMeasurementMappingError("artifact_channel_mismatch")
        artifact = _object(waveform.get("artifact"))
        time_range = _list(waveform.get("time_range_seconds"))
        voltage_range = _list(waveform.get("voltage_range_v"))
        try:
            reference = ArtifactReference(
                artifact_id=_uuid(artifact.get("artifact_id")),
                uri=_text(artifact.get("uri")),
                media_type=_text(artifact.get("media_type")),
                size_bytes=artifact.get("size_bytes"),
                sha256=artifact.get("sha256"),
            )
            return WaveformArtifact(
                reference=reference,
                channel=expected_channel,
                point_count=waveform.get("point_count"),
                sample_interval_seconds=waveform.get("sample_interval_seconds"),
                time_start_seconds=time_range[0],
                time_end_seconds=time_range[1],
                minimum_voltage=voltage_range[0],
                maximum_voltage=voltage_range[1],
                acquisition_mode=_text(waveform.get("acquisition_mode")),
                captured_at=_timestamp(waveform.get("captured_at")),
            )
        except (IndexError, TypeError, ValueError) as error:
            raise CanonicalMeasurementMappingError("artifact_reference_invalid") from error


def _object(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CanonicalMeasurementMappingError("canonical_object_expected")
    return value


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise CanonicalMeasurementMappingError("canonical_array_expected")
    return value


def _strings(value: Any) -> list[str]:
    values = _list(value)
    if any(not isinstance(item, str) for item in values):
        raise CanonicalMeasurementMappingError("canonical_text_array_invalid")
    return values


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise CanonicalMeasurementMappingError("canonical_text_invalid")
    return value


def _optional_text(value: Any) -> str | None:
    return None if value is None else _text(value)


def _uuid(value: Any) -> UUID:
    try:
        return UUID(_text(value))
    except (TypeError, ValueError) as error:
        raise CanonicalMeasurementMappingError("canonical_uuid_invalid") from error


def _timestamp(value: Any) -> datetime:
    try:
        result = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise CanonicalMeasurementMappingError("canonical_timestamp_invalid") from error
    if result.utcoffset() is None:
        raise CanonicalMeasurementMappingError("canonical_timestamp_invalid")
    return result
