from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias
from uuid import UUID

from ..artifacts import ArtifactReference
from ..eda.models import DesignDocument, DesignObjectRef, ProbeTarget, SelectionContext
from ..errors import DomainInvariantError
from ..values import DutyCycle


class EvidenceCategory(StrEnum):
    DESIGN_FACT = "DESIGN_FACT"
    DESIGN_TARGET = "DESIGN_TARGET"
    PHYSICAL_FACT = "PHYSICAL_FACT"
    SOFTWARE_ANALYSIS = "SOFTWARE_ANALYSIS"
    SIMULATED_EVIDENCE = "SIMULATED_EVIDENCE"
    INFERENCE = "INFERENCE"


class TeachingEvidenceKind(StrEnum):
    FACT = "FACT"
    ANALYSIS = "ANALYSIS"
    INFERENCE = "INFERENCE"


class TeachingEvidenceSource(StrEnum):
    INSTRUMENT = "instrument"
    SOFTWARE_ANALYSIS = "software_analysis"
    SIMULATED = "simulated"


class EvidenceQuality(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ExecutionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ConfirmationState(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    CONFIRMED = "CONFIRMED"
    SIMULATED = "SIMULATED"


class RequiredUserAction(StrEnum):
    NONE = "NONE"
    EXPLICIT_REMEASURE_DECISION = "EXPLICIT_REMEASURE_DECISION"


TeachingValue: TypeAlias = float | str | DutyCycle | None


@dataclass(frozen=True, slots=True)
class TeachingEvidenceProvenance:
    method: str
    observed_at: datetime
    analysis_algorithm: str | None
    evidence_artifact_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "method", _text(self.method, "method"))
        _aware(self.observed_at, "observed_at")
        if self.analysis_algorithm is not None:
            object.__setattr__(
                self,
                "analysis_algorithm",
                _text(self.analysis_algorithm, "analysis_algorithm"),
            )
        values = tuple(self.evidence_artifact_ids)
        if not all(isinstance(value, UUID) for value in values):
            raise DomainInvariantError("evidence_artifact_ids must contain UUID values")
        if len(values) != len(set(values)):
            raise DomainInvariantError("evidence_artifact_ids must be unique")
        object.__setattr__(self, "evidence_artifact_ids", values)


@dataclass(frozen=True, slots=True)
class TeachingEvidenceItem:
    kind: TeachingEvidenceKind
    label: str
    value: TeachingValue
    unit: str | None
    source: TeachingEvidenceSource
    quality: EvidenceQuality
    warnings: tuple[str, ...]
    provenance: TeachingEvidenceProvenance

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TeachingEvidenceKind):
            raise DomainInvariantError("kind must be a TeachingEvidenceKind")
        if not isinstance(self.source, TeachingEvidenceSource):
            raise DomainInvariantError("source must be a TeachingEvidenceSource")
        if not isinstance(self.quality, EvidenceQuality):
            raise DomainInvariantError("quality must be an EvidenceQuality")
        object.__setattr__(self, "label", _text(self.label, "label"))
        if self.unit is not None:
            object.__setattr__(self, "unit", _text(self.unit, "unit"))
        if isinstance(self.value, bool) or not isinstance(
            self.value, (int, float, str, DutyCycle, type(None))
        ):
            raise DomainInvariantError("evidence value must be a bounded scalar or DutyCycle")
        if isinstance(self.value, (int, float)):
            object.__setattr__(self, "value", _finite(self.value, "value"))
        if isinstance(self.value, str) and len(self.value) > 4096:
            raise DomainInvariantError("large evidence text must use ArtifactReference")
        if self.quality is EvidenceQuality.UNAVAILABLE and self.value is not None:
            raise DomainInvariantError("unavailable evidence must have a null value")
        warnings = _texts(self.warnings, "warnings")
        object.__setattr__(self, "warnings", warnings)
        if not isinstance(self.provenance, TeachingEvidenceProvenance):
            raise DomainInvariantError("provenance must be TeachingEvidenceProvenance")

        if self.kind is TeachingEvidenceKind.FACT and self.source not in (
            TeachingEvidenceSource.INSTRUMENT,
            TeachingEvidenceSource.SIMULATED,
        ):
            raise DomainInvariantError("FACT source must be instrument or simulated")
        if self.kind is TeachingEvidenceKind.ANALYSIS and self.source not in (
            TeachingEvidenceSource.SOFTWARE_ANALYSIS,
            TeachingEvidenceSource.SIMULATED,
        ):
            raise DomainInvariantError(
                "ANALYSIS source must be software_analysis or simulated"
            )

    @property
    def category(self) -> EvidenceCategory:
        if self.source is TeachingEvidenceSource.SIMULATED:
            return EvidenceCategory.SIMULATED_EVIDENCE
        if self.kind is TeachingEvidenceKind.INFERENCE:
            return EvidenceCategory.INFERENCE
        if self.kind is TeachingEvidenceKind.FACT:
            return EvidenceCategory.PHYSICAL_FACT
        return EvidenceCategory.SOFTWARE_ANALYSIS


@dataclass(frozen=True, slots=True)
class EvidenceCoherence:
    software_observations: str
    instrument_vs_software: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "software_observations",
            _text(self.software_observations, "software_observations"),
        )
        object.__setattr__(
            self,
            "instrument_vs_software",
            _text(self.instrument_vs_software, "instrument_vs_software"),
        )


@dataclass(frozen=True, slots=True)
class OpaqueWaveformEvidence:
    reference: ArtifactReference
    channel: int
    point_count: int
    sample_interval_seconds: float
    time_range_seconds: tuple[float, float]
    voltage_range_v: tuple[float, float]
    acquisition_mode: str
    captured_at: datetime
    opaque: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ArtifactReference):
            raise DomainInvariantError("reference must be ArtifactReference")
        if self.channel not in (1, 2) or isinstance(self.channel, bool):
            raise DomainInvariantError("channel must be 1 or 2")
        if isinstance(self.point_count, bool) or not isinstance(self.point_count, int) or self.point_count < 1:
            raise DomainInvariantError("point_count must be a positive integer")
        interval = _finite(self.sample_interval_seconds, "sample_interval_seconds")
        if interval <= 0:
            raise DomainInvariantError("sample_interval_seconds must be positive")
        object.__setattr__(self, "sample_interval_seconds", interval)
        time_range = _numeric_pair(self.time_range_seconds, "time_range_seconds")
        voltage_range = _numeric_pair(self.voltage_range_v, "voltage_range_v")
        if time_range[1] < time_range[0] or voltage_range[1] < voltage_range[0]:
            raise DomainInvariantError("artifact ranges must be ordered")
        object.__setattr__(self, "time_range_seconds", time_range)
        object.__setattr__(self, "voltage_range_v", voltage_range)
        object.__setattr__(self, "acquisition_mode", _text(self.acquisition_mode, "acquisition_mode"))
        _aware(self.captured_at, "captured_at")
        if self.opaque is not True:
            raise DomainInvariantError("waveform evidence must remain opaque")


@dataclass(frozen=True, slots=True)
class InstrumentEvidenceSummary:
    manufacturer: str
    model: str
    serial_number: str
    firmware_version: str

    def __post_init__(self) -> None:
        for name in ("manufacturer", "model", "serial_number", "firmware_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class EvidenceFailure:
    code: str
    message: str
    delivery_state: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text(self.code, "code"))
        object.__setattr__(self, "message", _text(self.message, "message"))
        if self.delivery_state is not None:
            object.__setattr__(self, "delivery_state", _text(self.delivery_state, "delivery_state"))


@dataclass(frozen=True, slots=True)
class TeachingEvidenceContext:
    requested_goal: str
    measurement_decision_reason: str
    operation: str | None
    execution_status: ExecutionStatus
    confirmation_state: ConfirmationState
    required_user_action: RequiredUserAction
    instrument: InstrumentEvidenceSummary | None
    facts: tuple[TeachingEvidenceItem, ...]
    analyses: tuple[TeachingEvidenceItem, ...]
    inferences: tuple[TeachingEvidenceItem, ...]
    quality: str | None
    warnings: tuple[str, ...]
    coherence: EvidenceCoherence | None
    artifact: OpaqueWaveformEvidence | None
    limitations: tuple[str, ...]
    failure: EvidenceFailure | None
    allowed_inference_boundary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_goal", _text(self.requested_goal, "requested_goal"))
        object.__setattr__(self, "measurement_decision_reason", _text(self.measurement_decision_reason, "measurement_decision_reason"))
        if self.operation is not None:
            object.__setattr__(self, "operation", _text(self.operation, "operation"))
        if not isinstance(self.execution_status, ExecutionStatus):
            raise DomainInvariantError("execution_status must be ExecutionStatus")
        if not isinstance(self.confirmation_state, ConfirmationState):
            raise DomainInvariantError("confirmation_state must be ConfirmationState")
        if not isinstance(self.required_user_action, RequiredUserAction):
            raise DomainInvariantError("required_user_action must be RequiredUserAction")
        facts, analyses, inferences = tuple(self.facts), tuple(self.analyses), tuple(self.inferences)
        if any(item.kind is not TeachingEvidenceKind.FACT for item in facts):
            raise DomainInvariantError("facts must contain only FACT items")
        if any(item.kind is not TeachingEvidenceKind.ANALYSIS for item in analyses):
            raise DomainInvariantError("analyses must contain only ANALYSIS items")
        if any(item.kind is not TeachingEvidenceKind.INFERENCE for item in inferences):
            raise DomainInvariantError("inferences must contain only INFERENCE items")
        object.__setattr__(self, "facts", facts)
        object.__setattr__(self, "analyses", analyses)
        object.__setattr__(self, "inferences", inferences)
        if self.quality not in ("good", "degraded", "failed", None):
            raise DomainInvariantError("context quality is invalid")
        object.__setattr__(self, "warnings", _texts(self.warnings, "warnings"))
        object.__setattr__(self, "limitations", _texts(self.limitations, "limitations"))
        object.__setattr__(self, "allowed_inference_boundary", _text(self.allowed_inference_boundary, "allowed_inference_boundary"))


class DesignEvidenceKind(StrEnum):
    DOCUMENT_FACT = "DOCUMENT_FACT"
    CONNECTIVITY_FACT = "CONNECTIVITY_FACT"
    TARGET_DECLARATION = "TARGET_DECLARATION"


class DesignEvidenceOrigin(StrEnum):
    DESIGN_DERIVED = "DESIGN_DERIVED"
    USER_STATEMENT = "USER_STATEMENT"


class VerificationState(StrEnum):
    SNAPSHOT_BOUNDED = "SNAPSHOT_BOUNDED"
    USER_ASSERTED = "USER_ASSERTED"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True, slots=True)
class Quantity:
    value: float
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _finite(self.value, "quantity value"))
        object.__setattr__(self, "unit", _text(self.unit, "quantity unit"))


DesignValue: TypeAlias = Quantity | float | str | bool | None


@dataclass(frozen=True, slots=True)
class DesignEvidenceItem:
    evidence_id: UUID
    kind: DesignEvidenceKind
    label: str
    value: DesignValue
    unit: str | None
    document: DesignDocument
    design_object: DesignObjectRef | None
    verification_state: VerificationState
    observed_at: datetime
    origin: DesignEvidenceOrigin

    def __post_init__(self) -> None:
        _uuid(self.evidence_id, "evidence_id")
        if not isinstance(self.kind, DesignEvidenceKind):
            raise DomainInvariantError("kind must be DesignEvidenceKind")
        object.__setattr__(self, "label", _text(self.label, "label"))
        if self.unit is not None:
            object.__setattr__(self, "unit", _text(self.unit, "unit"))
        if isinstance(self.value, Quantity) and self.value.unit != self.unit:
            raise DomainInvariantError("Quantity unit must equal the evidence unit")
        if self.design_object is not None:
            doc = self.document.document_ref
            obj = self.design_object
            if (obj.provider, obj.document_id, obj.snapshot_id) != (doc.provider, doc.document_id, doc.snapshot_id):
                raise DomainInvariantError("design object must belong to the evidence document snapshot")
        if not isinstance(self.verification_state, VerificationState):
            raise DomainInvariantError("verification_state must be VerificationState")
        if not isinstance(self.origin, DesignEvidenceOrigin):
            raise DomainInvariantError("origin must be DesignEvidenceOrigin")
        _aware(self.observed_at, "observed_at")

    @property
    def category(self) -> EvidenceCategory:
        if self.kind is DesignEvidenceKind.TARGET_DECLARATION:
            return EvidenceCategory.DESIGN_TARGET
        return EvidenceCategory.DESIGN_FACT

    @property
    def native_revision(self) -> str | None:
        return self.document.native_revision

    @property
    def fingerprint(self):
        return self.document.fingerprint


class EngineeringMetric(StrEnum):
    FREQUENCY = "FREQUENCY"
    DUTY_CYCLE = "DUTY_CYCLE"
    VOLTAGE = "VOLTAGE"
    PERIOD = "PERIOD"
    STATE = "STATE"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class ExactNumericExpectation:
    quantity: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.quantity, Quantity):
            raise DomainInvariantError("exact numeric expectation requires Quantity")


@dataclass(frozen=True, slots=True)
class NumericRangeExpectation:
    minimum: float
    maximum: float
    unit: str

    def __post_init__(self) -> None:
        minimum = _finite(self.minimum, "minimum")
        maximum = _finite(self.maximum, "maximum")
        if maximum < minimum:
            raise DomainInvariantError("numeric range maximum must be >= minimum")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "unit", _text(self.unit, "unit"))


@dataclass(frozen=True, slots=True)
class DiscreteExpectation:
    value: str | bool

    def __post_init__(self) -> None:
        if isinstance(self.value, str):
            object.__setattr__(self, "value", _text(self.value, "value"))
        elif not isinstance(self.value, bool):
            raise DomainInvariantError("discrete expectation must be text or boolean")


TargetExpectation: TypeAlias = ExactNumericExpectation | NumericRangeExpectation | DiscreteExpectation


@dataclass(frozen=True, slots=True)
class AbsoluteTolerance:
    quantity: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.quantity, Quantity) or self.quantity.value < 0:
            raise DomainInvariantError("absolute tolerance must be a non-negative Quantity")


@dataclass(frozen=True, slots=True, init=False)
class RelativeTolerance:
    ratio: float

    def __init__(self) -> None:
        raise TypeError("Use RelativeTolerance.from_ratio() or from_percent()")

    @classmethod
    def from_ratio(cls, ratio: float) -> RelativeTolerance:
        value = _finite(ratio, "relative tolerance ratio")
        if value < 0:
            raise DomainInvariantError("relative tolerance ratio must be non-negative")
        result = object.__new__(cls)
        object.__setattr__(result, "ratio", value)
        return result

    @classmethod
    def from_percent(cls, percent: float) -> RelativeTolerance:
        value = _finite(percent, "relative tolerance percent")
        if value < 0:
            raise DomainInvariantError("relative tolerance percent must be non-negative")
        return cls.from_ratio(value / 100.0)


Tolerance: TypeAlias = AbsoluteTolerance | RelativeTolerance


class TargetProvenance(StrEnum):
    DESIGN_DERIVED = "DESIGN_DERIVED"
    USER_PROVIDED = "USER_PROVIDED"


@dataclass(frozen=True, slots=True)
class EngineeringTarget:
    target_id: UUID
    metric: EngineeringMetric
    expectation: TargetExpectation
    tolerance: Tolerance | None
    provenance: TargetProvenance
    source_evidence_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        _uuid(self.target_id, "target_id")
        if not isinstance(self.metric, EngineeringMetric):
            raise DomainInvariantError("metric must be EngineeringMetric")
        if not isinstance(self.expectation, (ExactNumericExpectation, NumericRangeExpectation, DiscreteExpectation)):
            raise DomainInvariantError("unsupported target expectation")
        if isinstance(self.expectation, (NumericRangeExpectation, DiscreteExpectation)) and self.tolerance is not None:
            raise DomainInvariantError("range/discrete expectations cannot add a second tolerance")
        if self.tolerance is not None and not isinstance(self.tolerance, (AbsoluteTolerance, RelativeTolerance)):
            raise DomainInvariantError("unsupported tolerance")
        if not isinstance(self.provenance, TargetProvenance):
            raise DomainInvariantError("provenance must be TargetProvenance")
        sources = tuple(self.source_evidence_ids)
        if not sources or not all(isinstance(value, UUID) for value in sources):
            raise DomainInvariantError("target must reference at least one source evidence UUID")
        if len(sources) != len(set(sources)):
            raise DomainInvariantError("source_evidence_ids must be unique")
        object.__setattr__(self, "source_evidence_ids", sources)

    @property
    def category(self) -> EvidenceCategory:
        return EvidenceCategory.DESIGN_TARGET


class CrossReferenceState(StrEnum):
    VERIFIED_LINK = "VERIFIED_LINK"
    UNVERIFIED_LINK = "UNVERIFIED_LINK"
    MISMATCH = "MISMATCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class TrustedPhysicalConfirmationEvidence:
    """Reference to Phase 7C trusted host state; it cannot authorize execution."""

    confirmation_id: str
    source: str
    confirmed_by: str
    workflow_id: str
    request_correlation_id: str
    channel: int
    target_ref: str
    design_snapshot_id: UUID
    probe_target_id: UUID
    safe_low_voltage_confirmed: bool
    common_ground_confirmed: bool
    wiring_unchanged: bool
    confirmed_at: datetime

    def __post_init__(self) -> None:
        for name in ("confirmation_id", "confirmed_by", "workflow_id", "request_correlation_id", "target_ref"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.source != "TRUSTED_USER_EVENT":
            raise DomainInvariantError("confirmation evidence source must be TRUSTED_USER_EVENT")
        if self.channel not in (1, 2) or isinstance(self.channel, bool):
            raise DomainInvariantError("confirmation channel must be 1 or 2")
        _uuid(self.design_snapshot_id, "design_snapshot_id")
        _uuid(self.probe_target_id, "probe_target_id")
        if not all((self.safe_low_voltage_confirmed, self.common_ground_confirmed, self.wiring_unchanged)):
            raise DomainInvariantError("trusted physical confirmation must preserve all safety confirmations")
        _aware(self.confirmed_at, "confirmed_at")


@dataclass(frozen=True, slots=True)
class EvidenceCrossReference:
    cross_reference_id: UUID
    state: CrossReferenceState
    reasons: tuple[str, ...]
    workflow_id: str
    probe_target_id: UUID | None
    design_snapshot_id: UUID | None
    confirmation_id: str | None
    confirmation_source: str | None
    confirmed_by: str | None
    confirmed_target_ref: str | None
    request_correlation_id: str | None
    measurement_context_id: UUID | None
    measurement_channel: int | None
    confirmed_at: datetime | None
    measured_at: datetime | None

    def __post_init__(self) -> None:
        _uuid(self.cross_reference_id, "cross_reference_id")
        if not isinstance(self.state, CrossReferenceState):
            raise DomainInvariantError("state must be CrossReferenceState")
        object.__setattr__(self, "workflow_id", _text(self.workflow_id, "workflow_id"))
        reasons = _texts(self.reasons, "reasons")
        object.__setattr__(self, "reasons", reasons)
        if self.state is CrossReferenceState.VERIFIED_LINK:
            required = (
                self.probe_target_id, self.design_snapshot_id, self.confirmation_id,
                self.confirmation_source, self.confirmed_by, self.confirmed_target_ref,
                self.request_correlation_id, self.measurement_context_id,
                self.measurement_channel, self.confirmed_at, self.measured_at,
            )
            if any(value is None for value in required) or reasons:
                raise DomainInvariantError("verified link requires complete, non-conflicting provenance")
            if self.confirmed_at > self.measured_at:
                raise DomainInvariantError("physical confirmation must not follow measurement")
        elif not reasons:
            raise DomainInvariantError("non-verified link requires bounded reasons")


class EvidenceCollection(StrEnum):
    FACTS = "facts"
    ANALYSES = "analyses"
    INFERENCES = "inferences"


@dataclass(frozen=True, slots=True)
class MeasurementEvidenceLocator:
    measurement_context_id: UUID
    collection: EvidenceCollection
    ordinal: int
    label: str
    metric: EngineeringMetric
    category: EvidenceCategory

    def __post_init__(self) -> None:
        _uuid(self.measurement_context_id, "measurement_context_id")
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise DomainInvariantError("ordinal must be a non-negative integer")
        object.__setattr__(self, "label", _text(self.label, "label"))


@dataclass(frozen=True, slots=True)
class LocatedEvidence:
    locator: MeasurementEvidenceLocator
    item: TeachingEvidenceItem

    def __post_init__(self) -> None:
        if self.locator.label != self.item.label or self.locator.category is not self.item.category:
            raise DomainInvariantError("measurement locator must describe the located evidence")
        expected_collection = {
            TeachingEvidenceKind.FACT: EvidenceCollection.FACTS,
            TeachingEvidenceKind.ANALYSIS: EvidenceCollection.ANALYSES,
            TeachingEvidenceKind.INFERENCE: EvidenceCollection.INFERENCES,
        }[self.item.kind]
        if self.locator.collection is not expected_collection:
            raise DomainInvariantError("measurement locator collection must match evidence kind")


class ComparisonStatus(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    INDETERMINATE = "INDETERMINATE"


class ComparisonReason(StrEnum):
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    OUTSIDE_TOLERANCE = "OUTSIDE_TOLERANCE"
    WITHIN_RANGE = "WITHIN_RANGE"
    OUTSIDE_RANGE = "OUTSIDE_RANGE"
    DISCRETE_EQUAL = "DISCRETE_EQUAL"
    DISCRETE_DIFFERENT = "DISCRETE_DIFFERENT"
    TOLERANCE_UNSPECIFIED = "TOLERANCE_UNSPECIFIED"
    MEASUREMENT_MISSING = "MEASUREMENT_MISSING"
    OBSERVATION_UNAVAILABLE = "OBSERVATION_UNAVAILABLE"
    INCOMPATIBLE_METRIC = "INCOMPATIBLE_METRIC"
    INCOMPATIBLE_UNIT = "INCOMPATIBLE_UNIT"
    NON_NUMERIC_OBSERVATION = "NON_NUMERIC_OBSERVATION"
    CROSS_REFERENCE_UNVERIFIED = "CROSS_REFERENCE_UNVERIFIED"
    RELATIVE_DIFFERENCE_UNDEFINED = "RELATIVE_DIFFERENCE_UNDEFINED"


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    metric: EngineeringMetric
    target_id: UUID
    observed_ref: MeasurementEvidenceLocator | None
    expected: TargetExpectation
    observed: Quantity | str | bool | None
    difference: Quantity | None
    relative_difference: float | None
    status: ComparisonStatus
    reason: ComparisonReason
    comparator_name: str = "aia.deterministic-explicit-tolerance"
    comparator_version: str = "1"

    def __post_init__(self) -> None:
        _uuid(self.target_id, "target_id")
        if not isinstance(self.status, ComparisonStatus) or not isinstance(self.reason, ComparisonReason):
            raise DomainInvariantError("comparison status/reason are invalid")
        if self.relative_difference is not None:
            object.__setattr__(self, "relative_difference", _finite(self.relative_difference, "relative_difference"))


@dataclass(frozen=True, slots=True)
class UnresolvedQuestion:
    code: str
    subject_ref: str | None
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _text(self.code, "code"))
        if self.subject_ref is not None:
            object.__setattr__(self, "subject_ref", _text(self.subject_ref, "subject_ref"))
        object.__setattr__(self, "detail", _text(self.detail, "detail"))


@dataclass(frozen=True, slots=True)
class DesignEvidenceContext:
    document: DesignDocument
    evidence: tuple[DesignEvidenceItem, ...]
    probe_targets: tuple[ProbeTarget, ...] = ()
    selection: SelectionContext | None = None

    def __post_init__(self) -> None:
        evidence, probes = tuple(self.evidence), tuple(self.probe_targets)
        if len({item.evidence_id for item in evidence}) != len(evidence):
            raise DomainInvariantError("design evidence identifiers must be unique")
        for item in evidence:
            if item.document != self.document:
                raise DomainInvariantError("design evidence must share the context document")
        for probe in probes:
            if probe.snapshot_id != self.document.snapshot_id:
                raise DomainInvariantError("probe targets must share the design snapshot")
        if self.selection is not None and self.selection.snapshot_id != self.document.snapshot_id:
            raise DomainInvariantError("selection must share the design snapshot")
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "probe_targets", probes)


@dataclass(frozen=True, slots=True)
class EngineeringEvidenceContext:
    context_id: UUID
    workflow_id: str
    user_goal: str
    assembled_at: datetime
    design_context: DesignEvidenceContext | None
    targets: tuple[EngineeringTarget, ...]
    measurement_context_id: UUID | None
    measurement_context: TeachingEvidenceContext | None
    cross_references: tuple[EvidenceCrossReference, ...]
    comparison_results: tuple[ComparisonResult, ...]
    limitations: tuple[str, ...]
    unresolved_questions: tuple[UnresolvedQuestion, ...]
    inferences: tuple[TeachingEvidenceItem, ...] = ()
    assembler_name: str = "aia.engineering-evidence-assembler"
    assembler_version: str = "1"

    def __post_init__(self) -> None:
        _uuid(self.context_id, "context_id")
        object.__setattr__(self, "workflow_id", _text(self.workflow_id, "workflow_id"))
        object.__setattr__(self, "user_goal", _text(self.user_goal, "user_goal"))
        _aware(self.assembled_at, "assembled_at")
        if (self.measurement_context_id is None) != (self.measurement_context is None):
            raise DomainInvariantError("measurement context and identifier must be present together")
        for name in ("targets", "cross_references", "comparison_results", "unresolved_questions"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "limitations", _texts(self.limitations, "limitations"))
        object.__setattr__(self, "assembler_name", _text(self.assembler_name, "assembler_name"))
        object.__setattr__(self, "assembler_version", _text(self.assembler_version, "assembler_version"))
        inferences = tuple(self.inferences)
        if inferences:
            raise DomainInvariantError("Phase 8A.2 deterministic context cannot contain INFERENCE")
        object.__setattr__(self, "inferences", inferences)


@dataclass(frozen=True, slots=True)
class CandidateNextMeasurement:
    metric: EngineeringMetric
    target_ref: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_ref", _text(self.target_ref, "target_ref"))
        object.__setattr__(self, "reason", _text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class TeachingDiagnosisContext:
    goal: str
    design_facts: tuple[DesignEvidenceItem, ...]
    design_targets: tuple[EngineeringTarget, ...]
    physical_observations: tuple[LocatedEvidence, ...]
    software_analyses: tuple[LocatedEvidence, ...]
    simulated_evidence: tuple[LocatedEvidence, ...]
    comparisons: tuple[ComparisonResult, ...]
    quality: str | None
    warnings: tuple[str, ...]
    coherence: EvidenceCoherence | None
    limitations: tuple[str, ...]
    unresolved_questions: tuple[UnresolvedQuestion, ...]
    candidate_next_measurements: tuple[CandidateNextMeasurement, ...] = ()
    inferences: tuple[TeachingEvidenceItem, ...] = ()


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainInvariantError(f"{name} must be non-empty text")
    return value.strip()


def _texts(values, name: str) -> tuple[str, ...]:
    result = tuple(_text(value, f"{name} item") for value in values)
    if len(result) != len(set(result)):
        raise DomainInvariantError(f"{name} must not contain duplicates")
    return result


def _finite(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainInvariantError(f"{name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise DomainInvariantError(f"{name} must be finite")
    return normalized


def _numeric_pair(values, name: str) -> tuple[float, float]:
    result = tuple(_finite(value, f"{name} item") for value in values)
    if len(result) != 2:
        raise DomainInvariantError(f"{name} must contain exactly two values")
    return result  # type: ignore[return-value]


def _uuid(value, name: str) -> None:
    if not isinstance(value, UUID):
        raise DomainInvariantError(f"{name} must be UUID")


def _aware(value, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise DomainInvariantError(f"{name} must be timezone-aware")
