from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from ai_instrument_assistant.application.experiments import (
    RCFrequencyPointMeasurement,
    RCLowPassMeasurementPlan,
    RCLowPassMeasurementPlanner,
)
from ai_instrument_assistant.application.reasoning import TeachingGoal
from ai_instrument_assistant.application.reasoning.publication import (
    CoordinatedPublicationResult,
    OneShotPublicationCoordinator,
)
from ai_instrument_assistant.domain.eda import (
    DesignDocument,
    DesignObjectKind,
    DesignObjectRef,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    DesignEvidenceItem,
    DesignEvidenceKind,
    DesignEvidenceOrigin,
    EngineeringMetric,
    EvidenceCoherence,
    EvidenceCollection,
    EvidenceQuality,
    LocatedEvidence,
    MeasurementEvidenceLocator,
    TeachingDiagnosisContext,
    TeachingEvidenceItem,
    TeachingEvidenceKind,
    TeachingEvidenceProvenance,
    TeachingEvidenceSource,
    UnresolvedQuestion,
    VerificationState,
)
from ai_instrument_assistant.domain.measurement import (
    MeasurementResult,
    ObservationQuality,
    ObservationSource,
)

# Teaching evidence keeps the observation's provenance distinct: a simulated
# backend observation must never be published as real instrument evidence.
_EVIDENCE_SOURCES = {
    ObservationSource.INSTRUMENT: TeachingEvidenceSource.INSTRUMENT,
    ObservationSource.SIMULATED: TeachingEvidenceSource.SIMULATED,
}
from ai_instrument_assistant.application.services.re001c_lite import (
    GovernedMeasurementBundle,
    map_and_analyze_governed_receipt,
)


_OPERATIONS = (
    ("hardware.measure_frequency", 1),
    ("hardware.measure_vpp", 1),
    ("hardware.measure_frequency", 2),
    ("hardware.measure_vpp", 2),
)
_INTENT = "RE001D_LITE_SINGLE_POINT"


class RE001DIntentError(ValueError):
    """The request is outside the one reviewed conversational experiment."""


@dataclass(frozen=True, slots=True)
class RE001DPreparedExperiment:
    intent: str
    user_request: str
    status: str
    plan: RCLowPassMeasurementPlan
    operation_sequence: tuple[tuple[str, int], ...]
    confirmation_prompt: str


@dataclass(frozen=True, slots=True)
class RE001DCompletion:
    prepared: RE001DPreparedExperiment
    measurement: RCFrequencyPointMeasurement
    teaching_context: TeachingDiagnosisContext
    publication: CoordinatedPublicationResult


class RE001DLiteCoordinator:
    """Two-stage validation composition; it owns neither authority nor hardware."""

    def prepare(self, user_request: str) -> RE001DPreparedExperiment:
        request = _bounded_request(user_request)
        _require_reviewed_intent(request)
        plan = RCLowPassMeasurementPlanner().from_user_declared_design(
            requested_frequency_hz=100.0,
            vin="STM32 output / CH1",
            vout="same STM32 output / CH2",
            reference="STM32 GND",
        )
        return RE001DPreparedExperiment(
            intent=_INTENT,
            user_request=request,
            status="CONFIRMATION_REQUIRED",
            plan=plan,
            operation_sequence=_OPERATIONS,
            confirmation_prompt=(
                "Confirm the STM32 signal is approximately 0–3.3 V, CH1 and CH2 "
                "probe tips are on the intended output, both references are on STM32 "
                "GND, no mains/high voltage is involved, and wiring will remain unchanged."
            ),
        )

    async def complete(
        self,
        prepared: RE001DPreparedExperiment,
        governed_receipt: Mapping[str, Any],
        *,
        publisher: OneShotPublicationCoordinator,
        correlation_id: str,
    ) -> RE001DCompletion:
        if not isinstance(prepared, RE001DPreparedExperiment) or prepared.intent != _INTENT:
            raise RE001DIntentError("prepared_experiment_invalid")
        bundle = map_and_analyze_governed_receipt(prepared.plan, governed_receipt)
        context = _teaching_context(prepared, bundle, correlation_id)
        publication = await publisher.publish(
            context=context,
            goal=TeachingGoal.EXPLAIN_MEASUREMENT,
            correlation_id=correlation_id,
        )
        return RE001DCompletion(prepared, bundle.analysis, context, publication)


def _bounded_request(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1_024:
        raise RE001DIntentError("bounded_request_required")
    return value.strip()


def _require_reviewed_intent(value: str) -> None:
    normalized = " ".join(value.casefold().replace("peak-to-peak", "vpp").split())
    required = ("measure", "ch1", "vin", "ch2", "vout", "frequency", "vpp", "explain")
    forbidden = ("waveform", "sweep", "duty", "pwm", "arbitrary", "scpi")
    if any(item not in normalized for item in required) or any(item in normalized for item in forbidden):
        raise RE001DIntentError("intent_outside_reviewed_flow")


def _teaching_context(
    prepared: RE001DPreparedExperiment,
    bundle: GovernedMeasurementBundle,
    correlation_id: str,
) -> TeachingDiagnosisContext:
    context_id = uuid5(NAMESPACE_URL, "aia:re001d:" + correlation_id)
    observed_at = max(item.provenance.completed_at for item in bundle.measurements)
    document = _user_document(context_id, observed_at)
    facts = tuple(
        DesignEvidenceItem(
            evidence_id=uuid5(context_id, "design-role:" + role),
            kind=DesignEvidenceKind.CONNECTIVITY_FACT,
            label=label,
            value=value,
            unit=None,
            document=document,
            design_object=None,
            verification_state=VerificationState.USER_ASSERTED,
            observed_at=observed_at,
            origin=DesignEvidenceOrigin.USER_STATEMENT,
        )
        for role, label, value in (
            ("vin", "Vin role", "STM32 output / CH1"),
            ("vout", "Vout role", "same STM32 output / CH2"),
            ("reference", "Reference role", "STM32 GND"),
        )
    )
    physical = tuple(
        _physical_item(context_id, ordinal, result)
        for ordinal, result in enumerate(bundle.measurements)
    )
    analysis = bundle.analysis
    software_values = (
        ("Vin/Vout gain ratio", analysis.gain_ratio, "ratio", EngineeringMetric.OTHER),
        ("Vin/Vout gain in decibels", analysis.gain_db, "dB", EngineeringMetric.OTHER),
        ("Vin frequency relative deviation", analysis.vin_frequency_relative_deviation, "ratio", EngineeringMetric.FREQUENCY),
        ("Vout frequency relative deviation", analysis.vout_frequency_relative_deviation, "ratio", EngineeringMetric.FREQUENCY),
    )
    software = tuple(
        _analysis_item(context_id, observed_at, ordinal, *value)
        for ordinal, value in enumerate(software_values)
    )
    warnings = tuple(dict.fromkeys(analysis.warnings))
    return TeachingDiagnosisContext(
        goal=prepared.user_request,
        design_facts=facts,
        design_targets=(),
        physical_observations=physical,
        software_analyses=software,
        simulated_evidence=(),
        comparisons=(),
        quality=analysis.quality.value,
        warnings=warnings,
        coherence=EvidenceCoherence(
            "deterministic_single_point_analysis",
            "sequential_same_session",
        ),
        limitations=(
            "No acceptance tolerance was supplied, so no compliance conclusion is available.",
            "The cause of any channel amplitude difference has not been established.",
        ),
        unresolved_questions=(UnresolvedQuestion(
            code="CHANNEL_AMPLITUDE_CAUSE_UNVERIFIED",
            subject_ref=None,
            detail=(
                "Whether source configuration, probe attenuation, or channel setup "
                "affects the readings remains an unverified troubleshooting question."
            ),
        ),),
        candidate_next_measurements=(),
        inferences=(),
    )


def _user_document(identity: UUID, observed_at: datetime) -> DesignDocument:
    return DesignDocument(
        document_ref=DesignObjectRef(
            provider="user-declared",
            object_type=DesignObjectKind.DOCUMENT,
            document_id="re001d-user-context",
            snapshot_id=identity,
            native_id=None,
            canonical_id="user-context/re001d",
            display_name="RE-001D user-declared context",
        ),
        project_id=None,
        project_name=None,
        document_name="RE-001D user-declared context",
        document_type="user_declared_context",
        native_revision=None,
        fingerprint=None,
        is_dirty=None,
        captured_at=observed_at,
    )


def _physical_item(context_id: UUID, ordinal: int, result: MeasurementResult) -> LocatedEvidence:
    observation = result.instrument_frequency or result.instrument_vpp
    if observation is None:
        raise ValueError("mapped_physical_observation_missing")
    metric = EngineeringMetric.FREQUENCY if result.instrument_frequency is not None else EngineeringMetric.VOLTAGE
    label = f"CH{result.request.channel} {'frequency' if metric is EngineeringMetric.FREQUENCY else 'Vpp'}"
    item = TeachingEvidenceItem(
        kind=TeachingEvidenceKind.FACT,
        label=label,
        value=observation.value,
        unit="Hz" if metric is EngineeringMetric.FREQUENCY else "V",
        source=_EVIDENCE_SOURCES[observation.source],
        quality=_evidence_quality(observation.quality),
        warnings=tuple(dict.fromkeys((*result.warnings, *observation.warnings))),
        provenance=TeachingEvidenceProvenance(
            method=observation.method,
            observed_at=observation.observed_at,
            analysis_algorithm=None,
            evidence_artifact_ids=observation.evidence_artifact_ids,
        ),
    )
    return LocatedEvidence(
        MeasurementEvidenceLocator(
            measurement_context_id=context_id,
            collection=EvidenceCollection.FACTS,
            ordinal=ordinal,
            label=label,
            metric=metric,
            category=item.category,
        ),
        item,
    )


def _analysis_item(
    context_id: UUID,
    observed_at: datetime,
    ordinal: int,
    label: str,
    value: float,
    unit: str,
    metric: EngineeringMetric,
) -> LocatedEvidence:
    item = TeachingEvidenceItem(
        kind=TeachingEvidenceKind.ANALYSIS,
        label=label,
        value=value,
        unit=unit,
        source=TeachingEvidenceSource.SOFTWARE_ANALYSIS,
        quality=EvidenceQuality.GOOD,
        warnings=(),
        provenance=TeachingEvidenceProvenance(
            method="deterministic RC single-point analysis",
            observed_at=observed_at,
            analysis_algorithm="aia.rc-single-point-analyzer/v1",
            evidence_artifact_ids=(),
        ),
    )
    return LocatedEvidence(
        MeasurementEvidenceLocator(
            measurement_context_id=context_id,
            collection=EvidenceCollection.ANALYSES,
            ordinal=ordinal,
            label=label,
            metric=metric,
            category=item.category,
        ),
        item,
    )


def _evidence_quality(value: ObservationQuality) -> EvidenceQuality:
    return {
        ObservationQuality.GOOD: EvidenceQuality.GOOD,
        ObservationQuality.DEGRADED: EvidenceQuality.DEGRADED,
        ObservationQuality.UNAVAILABLE: EvidenceQuality.UNAVAILABLE,
    }[value]
