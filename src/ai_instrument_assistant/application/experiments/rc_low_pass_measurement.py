from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from ai_instrument_assistant.domain.artifacts import ArtifactReference
from ai_instrument_assistant.domain.eda import DesignObjectRef
from ai_instrument_assistant.domain.measurement import (
    MeasurementKind,
    MeasurementQuality,
    MeasurementResult,
    ObservationQuality,
    ObservationSource,
)

from .rc_low_pass import RCExperimentReadiness, RCExperimentResult


class RCDesignContextSource(StrEnum):
    OBSERVED_DESIGN = "OBSERVED_DESIGN"
    USER_DECLARED_DESIGN_CONTEXT = "USER_DECLARED_DESIGN_CONTEXT"


class RCNodeRoleKind(StrEnum):
    VIN = "VIN"
    VOUT = "VOUT"
    REFERENCE = "REFERENCE"


class RCEvidenceSource(StrEnum):
    PHYSICAL_MEASUREMENT = "PHYSICAL_MEASUREMENT"
    SOFTWARE_ANALYSIS = "SOFTWARE_ANALYSIS"


class RCMeasurementAnalysisError(ValueError):
    """Bounded deterministic rejection of unusable measurement evidence."""


@dataclass(frozen=True, slots=True)
class RCNodeRole:
    role: RCNodeRoleKind
    source: RCDesignContextSource
    design_object: DesignObjectRef | None = None
    declared_label: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, RCNodeRoleKind):
            raise TypeError("role must be RCNodeRoleKind")
        if not isinstance(self.source, RCDesignContextSource):
            raise TypeError("source must be RCDesignContextSource")
        if self.source is RCDesignContextSource.OBSERVED_DESIGN:
            if not isinstance(self.design_object, DesignObjectRef) or self.declared_label is not None:
                raise ValueError("observed role requires only a design object")
        elif self.design_object is not None or self.declared_label is None:
            raise ValueError("user-declared role requires only a declared label")
        if self.declared_label is not None:
            object.__setattr__(self, "declared_label", _text(self.declared_label, "declared_label"))


@dataclass(frozen=True, slots=True)
class RCLowPassMeasurementPlan:
    requested_frequency_hz: float
    design_context_source: RCDesignContextSource
    vin_role: RCNodeRole
    vout_role: RCNodeRole
    reference_role: RCNodeRole
    manual_source_instructions: tuple[str, ...]
    experiment_type: str = "RC_LOW_PASS"
    vin_channel: int = 1
    vout_channel: int = 2

    def __post_init__(self) -> None:
        frequency = _positive_finite(self.requested_frequency_hz, "requested_frequency_hz")
        object.__setattr__(self, "requested_frequency_hz", frequency)
        if self.experiment_type != "RC_LOW_PASS":
            raise ValueError("only RC_LOW_PASS is supported")
        if self.vin_channel != 1 or self.vout_channel != 2:
            raise ValueError("RE-001B fixes Vin to CH1 and Vout to CH2")
        expected = (
            (self.vin_role, RCNodeRoleKind.VIN),
            (self.vout_role, RCNodeRoleKind.VOUT),
            (self.reference_role, RCNodeRoleKind.REFERENCE),
        )
        for role, kind in expected:
            if not isinstance(role, RCNodeRole) or role.role is not kind:
                raise ValueError("measurement-plan node roles are invalid")
            if role.source is not self.design_context_source:
                raise ValueError("all node roles must preserve the plan design provenance")
        instructions = tuple(_text(item, "manual_source_instruction") for item in self.manual_source_instructions)
        if not instructions or len(instructions) > 8:
            raise ValueError("manual source instructions must be a small non-empty tuple")
        object.__setattr__(self, "manual_source_instructions", instructions)

    @property
    def roles(self) -> tuple[RCNodeRole, RCNodeRole, RCNodeRole]:
        return self.vin_role, self.vout_role, self.reference_role


class RCLowPassMeasurementPlanner:
    def from_observed_design(
        self,
        design: RCExperimentResult,
        requested_frequency_hz: float,
    ) -> RCLowPassMeasurementPlan:
        if not isinstance(design, RCExperimentResult):
            raise TypeError("design must be RCExperimentResult")
        if (
            design.readiness is not RCExperimentReadiness.DESIGN_READY_FOR_MEASUREMENT
            or design.topology is None
        ):
            raise ValueError("observed design is not ready for a measurement plan")
        source = RCDesignContextSource.OBSERVED_DESIGN
        return self._plan(
            requested_frequency_hz,
            source,
            RCNodeRole(RCNodeRoleKind.VIN, source, design.topology.input_node.ref),
            RCNodeRole(RCNodeRoleKind.VOUT, source, design.topology.output_node.ref),
            RCNodeRole(RCNodeRoleKind.REFERENCE, source, design.topology.reference_node.ref),
        )

    def from_user_declared_design(
        self,
        *,
        requested_frequency_hz: float,
        vin: str,
        vout: str,
        reference: str,
    ) -> RCLowPassMeasurementPlan:
        source = RCDesignContextSource.USER_DECLARED_DESIGN_CONTEXT
        return self._plan(
            requested_frequency_hz,
            source,
            RCNodeRole(RCNodeRoleKind.VIN, source, declared_label=vin),
            RCNodeRole(RCNodeRoleKind.VOUT, source, declared_label=vout),
            RCNodeRole(RCNodeRoleKind.REFERENCE, source, declared_label=reference),
        )

    @staticmethod
    def _plan(
        requested_frequency_hz: float,
        source: RCDesignContextSource,
        vin: RCNodeRole,
        vout: RCNodeRole,
        reference: RCNodeRole,
    ) -> RCLowPassMeasurementPlan:
        frequency = _positive_finite(requested_frequency_hz, "requested_frequency_hz")
        return RCLowPassMeasurementPlan(
            requested_frequency_hz=frequency,
            design_context_source=source,
            vin_role=vin,
            vout_role=vout,
            reference_role=reference,
            manual_source_instructions=(
                f"Configure the signal source manually for a {frequency:g} Hz sine wave.",
                "Connect the source signal to Vin and its reference to circuit reference.",
                "Keep the source settings unchanged during this single-point measurement.",
            ),
        )


@dataclass(frozen=True, slots=True)
class RCPhysicalChannelMeasurement:
    channel: int
    frequency_hz: float
    vpp_v: float
    quality: MeasurementQuality
    artifacts: tuple[ArtifactReference, ...] = ()
    source: RCEvidenceSource = RCEvidenceSource.PHYSICAL_MEASUREMENT

    def __post_init__(self) -> None:
        if isinstance(self.channel, bool) or self.channel not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        object.__setattr__(self, "frequency_hz", _positive_finite(self.frequency_hz, "frequency_hz"))
        object.__setattr__(self, "vpp_v", _positive_finite(self.vpp_v, "vpp_v"))
        if self.quality not in (MeasurementQuality.GOOD, MeasurementQuality.DEGRADED):
            raise ValueError("physical channel quality must be usable")
        artifacts = tuple(self.artifacts)
        if not all(isinstance(item, ArtifactReference) for item in artifacts):
            raise TypeError("artifacts must contain ArtifactReference values")
        identifiers = tuple(item.artifact_id for item in artifacts)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("artifact references must be unique")
        object.__setattr__(self, "artifacts", artifacts)
        if self.source is not RCEvidenceSource.PHYSICAL_MEASUREMENT:
            raise ValueError("channel measurement source must remain physical")


@dataclass(frozen=True, slots=True)
class RCFrequencyPointMeasurement:
    requested_frequency_hz: float
    vin: RCPhysicalChannelMeasurement
    vout: RCPhysicalChannelMeasurement
    gain_ratio: float
    gain_db: float
    vin_frequency_relative_deviation: float
    vout_frequency_relative_deviation: float
    quality: MeasurementQuality
    warnings: tuple[str, ...] = ()
    within_tolerance: None = None
    analysis_source: RCEvidenceSource = RCEvidenceSource.SOFTWARE_ANALYSIS

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_frequency_hz", _positive_finite(self.requested_frequency_hz, "requested_frequency_hz"))
        if not isinstance(self.vin, RCPhysicalChannelMeasurement) or self.vin.channel != 1:
            raise ValueError("Vin measurement must be CH1")
        if not isinstance(self.vout, RCPhysicalChannelMeasurement) or self.vout.channel != 2:
            raise ValueError("Vout measurement must be CH2")
        for name in ("gain_ratio", "vin_frequency_relative_deviation", "vout_frequency_relative_deviation"):
            value = _finite(getattr(self, name), name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "gain_db", _finite(self.gain_db, "gain_db"))
        if self.quality not in (MeasurementQuality.GOOD, MeasurementQuality.DEGRADED):
            raise ValueError("frequency-point quality must be usable")
        warnings = tuple(_text(item, "warning") for item in self.warnings)
        if len(warnings) != len(set(warnings)):
            raise ValueError("warnings must be unique")
        object.__setattr__(self, "warnings", warnings)
        if self.within_tolerance is not None:
            raise ValueError("RE-001B cannot invent a tolerance conclusion")
        if self.analysis_source is not RCEvidenceSource.SOFTWARE_ANALYSIS:
            raise ValueError("gain must remain software analysis")


class RCSinglePointMeasurementAnalyzer:
    def analyze(
        self,
        plan: RCLowPassMeasurementPlan,
        *,
        vin_frequency: MeasurementResult | None,
        vout_frequency: MeasurementResult | None,
        vin_vpp: MeasurementResult | None,
        vout_vpp: MeasurementResult | None,
        vin_waveform: MeasurementResult | None = None,
        vout_waveform: MeasurementResult | None = None,
    ) -> RCFrequencyPointMeasurement:
        if not isinstance(plan, RCLowPassMeasurementPlan):
            raise TypeError("plan must be RCLowPassMeasurementPlan")
        vin_frequency_value = self._metric(vin_frequency, MeasurementKind.FREQUENCY, 1)
        vout_frequency_value = self._metric(vout_frequency, MeasurementKind.FREQUENCY, 2)
        vin_vpp_value = self._metric(vin_vpp, MeasurementKind.VPP, 1)
        vout_vpp_value = self._metric(vout_vpp, MeasurementKind.VPP, 2)
        if vin_vpp_value <= 0:
            raise RCMeasurementAnalysisError("vin_vpp_not_positive")
        if vout_vpp_value <= 0:
            raise RCMeasurementAnalysisError("vout_vpp_not_positive")

        vin_artifacts = self._artifacts(vin_waveform, 1)
        vout_artifacts = self._artifacts(vout_waveform, 2)
        inputs = (vin_frequency, vout_frequency, vin_vpp, vout_vpp)
        assert all(item is not None for item in inputs)
        usable_inputs = tuple(item for item in inputs if item is not None)
        quality = (
            MeasurementQuality.DEGRADED
            if any(item.quality is MeasurementQuality.DEGRADED for item in usable_inputs)
            else MeasurementQuality.GOOD
        )
        warnings = tuple(dict.fromkeys(
            warning
            for item in usable_inputs
            for warning in (
                *item.warnings,
                *(item.instrument_frequency.warnings if item.instrument_frequency is not None else ()),
                *(item.instrument_vpp.warnings if item.instrument_vpp is not None else ()),
            )
        ))
        gain_ratio = vout_vpp_value / vin_vpp_value
        return RCFrequencyPointMeasurement(
            requested_frequency_hz=plan.requested_frequency_hz,
            vin=RCPhysicalChannelMeasurement(1, vin_frequency_value, vin_vpp_value, quality, vin_artifacts),
            vout=RCPhysicalChannelMeasurement(2, vout_frequency_value, vout_vpp_value, quality, vout_artifacts),
            gain_ratio=gain_ratio,
            gain_db=20.0 * math.log10(gain_ratio),
            vin_frequency_relative_deviation=abs(vin_frequency_value - plan.requested_frequency_hz) / plan.requested_frequency_hz,
            vout_frequency_relative_deviation=abs(vout_frequency_value - plan.requested_frequency_hz) / plan.requested_frequency_hz,
            quality=quality,
            warnings=warnings,
        )

    @staticmethod
    def _metric(result: MeasurementResult | None, kind: MeasurementKind, channel: int) -> float:
        if result is None:
            raise RCMeasurementAnalysisError("measurement_missing")
        if not isinstance(result, MeasurementResult):
            raise RCMeasurementAnalysisError("measurement_type_invalid")
        if result.request.kind is not kind:
            raise RCMeasurementAnalysisError("measurement_kind_mismatch")
        if result.request.channel != channel:
            raise RCMeasurementAnalysisError("channel_mismatch")
        if result.quality is MeasurementQuality.FAILED:
            raise RCMeasurementAnalysisError("measurement_failed")
        observation = (
            result.instrument_frequency
            if kind is MeasurementKind.FREQUENCY
            else result.instrument_vpp
        )
        if observation is None or observation.value is None or observation.quality is ObservationQuality.UNAVAILABLE:
            raise RCMeasurementAnalysisError("measurement_unavailable")
        # Real instrument observations and honestly labelled simulated-backend
        # observations are both analyzable; their provenance stays distinct and
        # is preserved downstream by the evidence builder.
        if observation.source not in (ObservationSource.INSTRUMENT, ObservationSource.SIMULATED):
            raise RCMeasurementAnalysisError("measurement_not_physical")
        if isinstance(observation.value, bool) or not isinstance(observation.value, (int, float)):
            raise RCMeasurementAnalysisError("measurement_value_invalid")
        value = float(observation.value)
        if not math.isfinite(value):
            raise RCMeasurementAnalysisError("measurement_not_finite")
        if kind is MeasurementKind.FREQUENCY and value <= 0:
            raise RCMeasurementAnalysisError("frequency_not_positive")
        return value

    @staticmethod
    def _artifacts(result: MeasurementResult | None, channel: int) -> tuple[ArtifactReference, ...]:
        if result is None:
            return ()
        if not isinstance(result, MeasurementResult) or result.request.kind is not MeasurementKind.WAVEFORM:
            raise RCMeasurementAnalysisError("waveform_result_invalid")
        if result.request.channel != channel:
            raise RCMeasurementAnalysisError("channel_mismatch")
        if result.quality is MeasurementQuality.FAILED or result.waveform is None:
            raise RCMeasurementAnalysisError("waveform_unavailable")
        return (result.waveform.reference,)


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _positive_finite(value: float, name: str) -> float:
    normalized = _finite(value, name)
    if normalized <= 0:
        raise ValueError(f"{name} must be positive")
    return normalized


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 512:
        raise ValueError(f"{name} must be bounded non-empty text")
    return value.strip()
