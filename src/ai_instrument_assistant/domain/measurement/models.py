from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ai_instrument_assistant.domain.artifacts import WaveformArtifact
from ai_instrument_assistant.domain.errors import DomainInvariantError
from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.domain.values import DutyCycle


class MeasurementKind(StrEnum):
    FREQUENCY = "frequency"
    VPP = "vpp"
    WAVEFORM = "waveform"
    PWM = "pwm"


class ObservationSource(StrEnum):
    INSTRUMENT = "instrument"
    SOFTWARE_ANALYSIS = "software_analysis"
    SIMULATED = "simulated"


class ObservationQuality(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class MeasurementQuality(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    FAILED = "failed"


class CoherenceKind(StrEnum):
    SAME_ARTIFACT = "same_artifact"
    SEQUENTIAL_SAME_SESSION = "sequential_same_session"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MeasurementRequest:
    request_id: UUID
    kind: MeasurementKind
    channel: int
    context_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, UUID):
            raise DomainInvariantError("request_id must be a UUID")
        if not isinstance(self.kind, MeasurementKind):
            raise DomainInvariantError("kind must be a MeasurementKind")
        if isinstance(self.channel, bool) or self.channel not in (1, 2):
            raise DomainInvariantError("channel must be 1 or 2")
        if self.context_id is not None:
            object.__setattr__(self, "context_id", _text(self.context_id, "context_id"))


@dataclass(frozen=True, slots=True)
class MeasurementObservation:
    value: float | DutyCycle | None
    source: ObservationSource
    method: str
    observed_at: datetime
    quality: ObservationQuality
    warnings: tuple[str, ...] = ()
    evidence_artifact_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source, ObservationSource):
            raise DomainInvariantError("source must be an ObservationSource")
        object.__setattr__(self, "method", _text(self.method, "method"))
        _aware(self.observed_at, "observed_at")
        if not isinstance(self.quality, ObservationQuality):
            raise DomainInvariantError("quality must be an ObservationQuality")
        if self.value is None:
            if self.quality is not ObservationQuality.UNAVAILABLE:
                raise DomainInvariantError("an observation without a value must be unavailable")
        elif self.quality is ObservationQuality.UNAVAILABLE:
            raise DomainInvariantError("an unavailable observation cannot contain a value")
        elif isinstance(self.value, DutyCycle):
            pass
        elif isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise DomainInvariantError("observation value must be numeric, DutyCycle, or None")
        elif not math.isfinite(float(self.value)):
            raise DomainInvariantError("observation numeric value must be finite")
        else:
            object.__setattr__(self, "value", float(self.value))

        warnings = tuple(_text(value, "warning") for value in self.warnings)
        if len(warnings) != len(set(warnings)):
            raise DomainInvariantError("observation warnings must be unique")
        object.__setattr__(self, "warnings", warnings)
        evidence = tuple(self.evidence_artifact_ids)
        if any(not isinstance(identifier, UUID) for identifier in evidence):
            raise DomainInvariantError("evidence artifact identifiers must be UUIDs")
        if len(evidence) != len(set(evidence)):
            raise DomainInvariantError("evidence artifact identifiers must be unique")
        object.__setattr__(self, "evidence_artifact_ids", evidence)


@dataclass(frozen=True, slots=True)
class MeasurementCoherence:
    software_observations: CoherenceKind
    instrument_vs_software: CoherenceKind

    def __post_init__(self) -> None:
        if self.software_observations not in (
            CoherenceKind.SAME_ARTIFACT,
            CoherenceKind.UNKNOWN,
        ):
            raise DomainInvariantError("software coherence must be same_artifact or unknown")
        if self.instrument_vs_software not in (
            CoherenceKind.SEQUENTIAL_SAME_SESSION,
            CoherenceKind.UNKNOWN,
        ):
            raise DomainInvariantError(
                "cross-source coherence must be sequential_same_session or unknown"
            )

    @classmethod
    def unknown(cls) -> MeasurementCoherence:
        return cls(CoherenceKind.UNKNOWN, CoherenceKind.UNKNOWN)


@dataclass(frozen=True, slots=True)
class MeasurementProvenance:
    instrument_identity: InstrumentIdentity
    channel: int
    started_at: datetime
    completed_at: datetime
    analysis_algorithm_name: str | None = None
    analysis_algorithm_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_identity, InstrumentIdentity):
            raise DomainInvariantError("instrument_identity must be InstrumentIdentity")
        if isinstance(self.channel, bool) or self.channel not in (1, 2):
            raise DomainInvariantError("provenance channel must be 1 or 2")
        _aware(self.started_at, "started_at")
        _aware(self.completed_at, "completed_at")
        if self.completed_at < self.started_at:
            raise DomainInvariantError("completed_at cannot precede started_at")
        if (self.analysis_algorithm_name is None) != (self.analysis_algorithm_version is None):
            raise DomainInvariantError("analysis algorithm name and version must coexist")
        if self.analysis_algorithm_name is not None:
            object.__setattr__(self, "analysis_algorithm_name", _text(
                self.analysis_algorithm_name, "analysis_algorithm_name"
            ))
            object.__setattr__(self, "analysis_algorithm_version", _text(
                self.analysis_algorithm_version, "analysis_algorithm_version"
            ))


@dataclass(frozen=True, slots=True)
class MeasurementResult:
    request: MeasurementRequest
    waveform: WaveformArtifact | None
    quality: MeasurementQuality
    warnings: tuple[str, ...]
    coherence: MeasurementCoherence
    provenance: MeasurementProvenance
    instrument_frequency: MeasurementObservation | None = None
    instrument_vpp: MeasurementObservation | None = None
    software_frequency: MeasurementObservation | None = None
    software_period: MeasurementObservation | None = None
    software_duty_cycle: MeasurementObservation | None = None
    software_vpp: MeasurementObservation | None = None
    software_mean: MeasurementObservation | None = None
    software_rms: MeasurementObservation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, MeasurementRequest):
            raise DomainInvariantError("request must be a MeasurementRequest")
        if self.waveform is not None and not isinstance(self.waveform, WaveformArtifact):
            raise DomainInvariantError("waveform must be a WaveformArtifact or None")
        if not isinstance(self.quality, MeasurementQuality):
            raise DomainInvariantError("quality must be a MeasurementQuality")
        if not isinstance(self.coherence, MeasurementCoherence):
            raise DomainInvariantError("coherence must be MeasurementCoherence")
        if not isinstance(self.provenance, MeasurementProvenance):
            raise DomainInvariantError("provenance must be MeasurementProvenance")
        if self.request.channel != self.provenance.channel:
            raise DomainInvariantError("request and provenance channels must match")
        if self.waveform is not None and self.waveform.channel != self.request.channel:
            raise DomainInvariantError("waveform and request channels must match")
        warnings = tuple(_text(value, "warning") for value in self.warnings)
        if len(warnings) != len(set(warnings)):
            raise DomainInvariantError("result warnings must be unique")
        object.__setattr__(self, "warnings", warnings)

        for name in ("instrument_frequency", "instrument_vpp"):
            observation = getattr(self, name)
            if observation is not None and observation.source is not ObservationSource.INSTRUMENT:
                raise DomainInvariantError(f"{name} must have instrument source")
        for name in (
            "software_frequency", "software_period", "software_duty_cycle",
            "software_vpp", "software_mean", "software_rms",
        ):
            observation = getattr(self, name)
            if observation is not None and observation.source is not ObservationSource.SOFTWARE_ANALYSIS:
                raise DomainInvariantError(f"{name} must have software_analysis source")
        duty = self.software_duty_cycle
        if duty is not None and duty.value is not None and not isinstance(duty.value, DutyCycle):
            raise DomainInvariantError("software_duty_cycle must contain DutyCycle")


@dataclass(frozen=True, slots=True)
class InstrumentStatus:
    identity: InstrumentIdentity
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.identity, InstrumentIdentity):
            raise DomainInvariantError("identity must be InstrumentIdentity")
        _aware(self.observed_at, "observed_at")


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainInvariantError(f"{field_name} must be non-empty text")
    normalized = value.strip()
    if len(normalized) > 512:
        raise DomainInvariantError(f"{field_name} must be bounded text")
    return normalized


def _aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise DomainInvariantError(f"{field_name} must be timezone-aware")
