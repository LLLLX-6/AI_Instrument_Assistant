from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ai_instrument_assistant.analysis.models import AnalysisQuality, WaveformAnalysisResult
from ai_instrument_assistant.application.ports.artifact_store import ArtifactStore
from ai_instrument_assistant.application.ports.oscilloscope import OscilloscopeInterface
from ai_instrument_assistant.application.ports.waveform_analysis import WaveformAnalysisEngine
from ai_instrument_assistant.domain.artifacts import WaveformArtifact
from ai_instrument_assistant.domain.instrument import HardwareError, InstrumentIdentity
from ai_instrument_assistant.domain.instrument.waveform import Waveform
from ai_instrument_assistant.domain.measurement import (
    CoherenceKind,
    InstrumentStatus,
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

from .errors import AnalysisFailedError, ArtifactUnavailableError


class MeasurementService:
    """Compose semantic scope operations without depending on a concrete driver."""

    def __init__(
        self,
        *,
        oscilloscope: OscilloscopeInterface,
        analyzer: WaveformAnalysisEngine,
        artifact_store: ArtifactStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        instrument_observation_source: ObservationSource = ObservationSource.INSTRUMENT,
    ) -> None:
        if instrument_observation_source not in (
            ObservationSource.INSTRUMENT,
            ObservationSource.SIMULATED,
        ):
            raise ValueError(
                "instrument_observation_source must be instrument or simulated"
            )
        self._oscilloscope = oscilloscope
        self._analyzer = analyzer
        self._artifact_store = artifact_store
        self._clock = clock
        self._instrument_observation_source = instrument_observation_source

    def get_status(self) -> InstrumentStatus:
        return InstrumentStatus(
            identity=self._oscilloscope.get_identity(),
            observed_at=self._now(),
        )

    def measure(self, request: MeasurementRequest) -> MeasurementResult:
        if not isinstance(request, MeasurementRequest):
            raise TypeError("request must be a MeasurementRequest")
        identity = self._oscilloscope.get_identity()
        started_at = self._now()
        if request.kind is MeasurementKind.FREQUENCY:
            return self._single_instrument_measurement(
                request, identity, started_at, "frequency"
            )
        if request.kind is MeasurementKind.VPP:
            return self._single_instrument_measurement(
                request, identity, started_at, "vpp"
            )
        if request.kind is MeasurementKind.WAVEFORM:
            return self._waveform_measurement(request, identity, started_at)
        if request.kind is MeasurementKind.PWM:
            return self._pwm_measurement(request, identity, started_at)
        raise ValueError("unsupported measurement kind")

    def _single_instrument_measurement(
        self,
        request: MeasurementRequest,
        identity: InstrumentIdentity,
        started_at: datetime,
        metric: str,
    ) -> MeasurementResult:
        warning = f"instrument_{metric}_unavailable"
        try:
            value = (
                self._oscilloscope.measure_frequency(request.channel)
                if metric == "frequency"
                else self._oscilloscope.measure_vpp(request.channel)
            )
        except HardwareError:
            observation = self._unavailable(
                self._instrument_observation_source,
                f"oscilloscope.measure_{metric}",
                (warning,),
            )
            quality = MeasurementQuality.FAILED
            warnings = (warning,)
        else:
            observation = self._observed(
                value,
                self._instrument_observation_source,
                f"oscilloscope.measure_{metric}",
            )
            quality = MeasurementQuality.GOOD
            warnings = ()
        fields = {
            "instrument_frequency": observation if metric == "frequency" else None,
            "instrument_vpp": observation if metric == "vpp" else None,
        }
        return MeasurementResult(
            request=request,
            waveform=None,
            quality=quality,
            warnings=warnings,
            coherence=MeasurementCoherence.unknown(),
            provenance=self._provenance(identity, request.channel, started_at),
            **fields,
        )

    def _waveform_measurement(
        self,
        request: MeasurementRequest,
        identity: InstrumentIdentity,
        started_at: datetime,
    ) -> MeasurementResult:
        try:
            waveform = self._oscilloscope.capture_waveform(request.channel)
        except HardwareError:
            return MeasurementResult(
                request=request,
                waveform=None,
                quality=MeasurementQuality.FAILED,
                warnings=("waveform_unavailable",),
                coherence=MeasurementCoherence.unknown(),
                provenance=self._provenance(identity, request.channel, started_at),
            )
        artifact = self._store_waveform(waveform)
        return MeasurementResult(
            request=request,
            waveform=artifact,
            quality=MeasurementQuality.GOOD,
            warnings=(),
            coherence=MeasurementCoherence.unknown(),
            provenance=self._provenance(identity, request.channel, started_at),
        )

    def _pwm_measurement(
        self,
        request: MeasurementRequest,
        identity: InstrumentIdentity,
        started_at: datetime,
    ) -> MeasurementResult:
        try:
            waveform = self._oscilloscope.capture_waveform(request.channel)
        except HardwareError:
            warning = "waveform_unavailable"
            unavailable = {
                name: self._unavailable(
                    ObservationSource.SOFTWARE_ANALYSIS,
                    "waveform_analysis.not_run",
                    (warning,),
                )
                for name in (
                    "software_frequency", "software_period", "software_duty_cycle",
                    "software_vpp", "software_mean", "software_rms",
                )
            }
            return MeasurementResult(
                request=request,
                waveform=None,
                quality=MeasurementQuality.FAILED,
                warnings=(warning,),
                coherence=MeasurementCoherence.unknown(),
                provenance=self._provenance(identity, request.channel, started_at),
                **unavailable,
            )

        artifact = self._store_waveform(waveform)
        try:
            analysis = self._analyzer.analyze(waveform)
        except Exception as error:
            raise AnalysisFailedError("waveform analysis failed") from error
        software = self._software_observations(analysis, artifact)
        instrument_frequency = self._try_instrument_observation(
            lambda: self._oscilloscope.measure_frequency(request.channel),
            "oscilloscope.measure_frequency",
            "instrument_frequency_unavailable",
        )
        instrument_vpp = self._try_instrument_observation(
            lambda: self._oscilloscope.measure_vpp(request.channel),
            "oscilloscope.measure_vpp",
            "instrument_vpp_unavailable",
        )

        warnings = list(warning.value for warning in analysis.warnings)
        for observation in (instrument_frequency, instrument_vpp):
            for warning in observation.warnings:
                if warning not in warnings:
                    warnings.append(warning)
        quality = MeasurementQuality.GOOD
        if analysis.quality is not AnalysisQuality.GOOD or any(
            observation.quality is ObservationQuality.UNAVAILABLE
            for observation in (instrument_frequency, instrument_vpp)
        ):
            quality = MeasurementQuality.DEGRADED
        return MeasurementResult(
            request=request,
            waveform=artifact,
            instrument_frequency=instrument_frequency,
            instrument_vpp=instrument_vpp,
            quality=quality,
            warnings=tuple(warnings),
            coherence=MeasurementCoherence(
                CoherenceKind.SAME_ARTIFACT,
                CoherenceKind.SEQUENTIAL_SAME_SESSION,
            ),
            provenance=self._provenance(
                identity,
                request.channel,
                started_at,
                analysis.algorithm.name,
                analysis.algorithm.version,
            ),
            **software,
        )

    def _software_observations(
        self,
        analysis: WaveformAnalysisResult,
        artifact: WaveformArtifact,
    ) -> dict[str, MeasurementObservation]:
        method = f"{analysis.algorithm.name}/{analysis.algorithm.version}"
        warnings = tuple(warning.value for warning in analysis.warnings)
        evidence = (artifact.reference.artifact_id,)
        present_quality = (
            ObservationQuality.GOOD
            if analysis.quality is AnalysisQuality.GOOD
            else ObservationQuality.DEGRADED
        )

        def observation(value: object) -> MeasurementObservation:
            if value is None:
                return self._unavailable(
                    ObservationSource.SOFTWARE_ANALYSIS,
                    method,
                    warnings or ("software_metric_unavailable",),
                    evidence,
                )
            return MeasurementObservation(
                value=value,  # type: ignore[arg-type]
                source=ObservationSource.SOFTWARE_ANALYSIS,
                method=method,
                observed_at=self._now(),
                quality=present_quality,
                warnings=warnings,
                evidence_artifact_ids=evidence,
            )

        return {
            "software_frequency": observation(analysis.frequency_hz),
            "software_period": observation(analysis.period_s),
            "software_duty_cycle": observation(analysis.duty_cycle),
            "software_vpp": observation(analysis.vpp_v),
            "software_mean": observation(analysis.mean_v),
            "software_rms": observation(analysis.rms_v),
        }

    def _try_instrument_observation(
        self,
        operation: Callable[[], float],
        method: str,
        warning: str,
    ) -> MeasurementObservation:
        try:
            value = operation()
        except HardwareError:
            return self._unavailable(
                self._instrument_observation_source, method, (warning,)
            )
        return self._observed(value, self._instrument_observation_source, method)

    def _store_waveform(self, waveform: Waveform) -> WaveformArtifact:
        try:
            return self._artifact_store.put(waveform)
        except Exception as error:
            raise ArtifactUnavailableError("waveform artifact storage failed") from error

    def _observed(
        self,
        value: float,
        source: ObservationSource,
        method: str,
    ) -> MeasurementObservation:
        return MeasurementObservation(
            value=value,
            source=source,
            method=method,
            observed_at=self._now(),
            quality=ObservationQuality.GOOD,
        )

    def _unavailable(
        self,
        source: ObservationSource,
        method: str,
        warnings: tuple[str, ...],
        evidence: tuple = (),
    ) -> MeasurementObservation:
        return MeasurementObservation(
            value=None,
            source=source,
            method=method,
            observed_at=self._now(),
            quality=ObservationQuality.UNAVAILABLE,
            warnings=warnings,
            evidence_artifact_ids=evidence,
        )

    def _provenance(
        self,
        identity: InstrumentIdentity,
        channel: int,
        started_at: datetime,
        algorithm_name: str | None = None,
        algorithm_version: str | None = None,
    ) -> MeasurementProvenance:
        return MeasurementProvenance(
            instrument_identity=identity,
            channel=channel,
            started_at=started_at,
            completed_at=self._now(),
            analysis_algorithm_name=algorithm_name,
            analysis_algorithm_version=algorithm_version,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value
