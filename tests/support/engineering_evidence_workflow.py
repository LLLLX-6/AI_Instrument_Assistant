from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from ai_instrument_assistant.application.services.engineering_evidence_workflow import (
    EngineeringEvidenceWorkflowRequest,
)
from ai_instrument_assistant.domain.artifacts import ArtifactReference
from ai_instrument_assistant.domain.eda.models import (
    DesignDocument,
    DesignFingerprint,
    DesignObjectKind,
    DesignObjectRef,
    ProbeTarget,
    ProbeTargetKind,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    ConfirmationState,
    DesignEvidenceContext,
    DesignEvidenceItem,
    DesignEvidenceKind,
    DesignEvidenceOrigin,
    EngineeringMetric,
    EngineeringTarget,
    EvidenceCoherence,
    EvidenceQuality,
    ExactNumericExpectation,
    ExecutionStatus,
    InstrumentEvidenceSummary,
    OpaqueWaveformEvidence,
    Quantity,
    RelativeTolerance,
    RequiredUserAction,
    TargetProvenance,
    TeachingEvidenceContext,
    TeachingEvidenceItem,
    TeachingEvidenceKind,
    TeachingEvidenceProvenance,
    TeachingEvidenceSource,
    TrustedPhysicalConfirmationEvidence,
    VerificationState,
)
from ai_instrument_assistant.domain.values import DutyCycle


ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = json.loads(
    (ROOT / "tests" / "fixtures" / "evidence_workflow" / "scenarios.json").read_text(
        encoding="utf-8"
    )
)
NOW = datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc)
SNAPSHOT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
MEASUREMENT_CONTEXT_ID = UUID("abababab-abab-4bab-8bab-abababababab")
WORKFLOW_CONTEXT_ID = UUID("88888888-8888-4888-8888-888888888888")
PROBE_TARGET_ID = UUID("12121212-1212-4121-8121-121212121212")


def workflow_request(
    scenario_name: str,
    *,
    omit_targets: bool = False,
    omit_measurement: bool = False,
) -> EngineeringEvidenceWorkflowRequest:
    scenario = SCENARIOS[scenario_name]
    document = _document()
    probe = _probe()
    evidence: list[DesignEvidenceItem] = []
    targets: list[EngineeringTarget] = []
    if not omit_targets:
        for index, raw in enumerate(scenario["targets"]):
            evidence_id = UUID(f"bbbbbbbb-bbbb-4bbb-8bbb-{index + 1:012d}")
            quantity = Quantity(raw["value"], raw["unit"])
            evidence.append(
                DesignEvidenceItem(
                    evidence_id=evidence_id,
                    kind=DesignEvidenceKind.TARGET_DECLARATION,
                    label=f"PWM_OUT expected {raw['metric'].lower()}",
                    value=quantity,
                    unit=quantity.unit,
                    document=document,
                    design_object=probe.design_object,
                    verification_state=VerificationState.SNAPSHOT_BOUNDED,
                    observed_at=NOW,
                    origin=DesignEvidenceOrigin.DESIGN_DERIVED,
                )
            )
            tolerance = raw["tolerance"]
            targets.append(
                EngineeringTarget(
                    target_id=UUID(f"cccccccc-cccc-4ccc-8ccc-{index + 1:012d}"),
                    metric=EngineeringMetric(raw["metric"]),
                    expectation=ExactNumericExpectation(quantity),
                    tolerance=None if tolerance is None else RelativeTolerance.from_percent(tolerance["percent"]),
                    provenance=TargetProvenance.DESIGN_DERIVED,
                    source_evidence_ids=(evidence_id,),
                )
            )

    measurement = None if omit_measurement else _teaching_context(scenario)
    confirmation = _confirmation(scenario["confirmation"])
    return EngineeringEvidenceWorkflowRequest(
        context_id=WORKFLOW_CONTEXT_ID,
        workflow_id="phase8b1-fixture",
        request_correlation_id="request-1",
        user_goal="Compare PWM_OUT measurements with design targets",
        assembled_at=NOW + timedelta(seconds=4),
        design_context=DesignEvidenceContext(
            document=document,
            evidence=tuple(evidence),
            probe_targets=(probe,),
            selection=None,
        ),
        targets=tuple(targets),
        probe_target=probe,
        confirmation=confirmation,
        measurement_context_id=None if omit_measurement else MEASUREMENT_CONTEXT_ID,
        measurement_context=measurement,
        measurement_channel=None if omit_measurement else scenario["measurement_channel"],
        measured_at=None if omit_measurement else NOW + timedelta(seconds=2),
    )


def _document() -> DesignDocument:
    ref = DesignObjectRef(
        provider="recorded-fixture",
        object_type=DesignObjectKind.DOCUMENT,
        document_id="main_schematic",
        snapshot_id=SNAPSHOT_ID,
        native_id=None,
        canonical_id="project/document/main_schematic",
        display_name="main_schematic",
    )
    return DesignDocument(
        document_ref=ref,
        project_id="STM32_Test",
        project_name="STM32_Test",
        document_name="main_schematic",
        document_type="schematic",
        native_revision=None,
        fingerprint=DesignFingerprint(
            value="sha256:bounded",
            scope_kind="document_projection",
            scope_version="1",
            included_paths=("document", "selection"),
        ),
        is_dirty=False,
        captured_at=NOW,
    )


def _probe() -> ProbeTarget:
    return ProbeTarget(
        target_id=PROBE_TARGET_ID,
        design_object=DesignObjectRef(
            provider="recorded-fixture",
            object_type=DesignObjectKind.NET,
            document_id="main_schematic",
            snapshot_id=SNAPSHOT_ID,
            native_id=None,
            canonical_id="net/PWM_OUT",
            display_name="PWM_OUT",
        ),
        kind=ProbeTargetKind.DESIGN_ONLY,
    )


def _confirmation(raw) -> TrustedPhysicalConfirmationEvidence | None:
    if not raw["present"]:
        return None
    return TrustedPhysicalConfirmationEvidence(
        confirmation_id="confirmation-1",
        source="TRUSTED_USER_EVENT",
        confirmed_by="recorded-user-event",
        workflow_id="phase8b1-fixture",
        request_correlation_id="request-1",
        channel=raw["channel"],
        target_ref=raw["target_ref"],
        design_snapshot_id=UUID(raw["snapshot"]),
        probe_target_id=PROBE_TARGET_ID,
        safe_low_voltage_confirmed=True,
        common_ground_confirmed=True,
        wiring_unchanged=True,
        confirmed_at=NOW + timedelta(seconds=1),
    )


def _teaching_context(raw) -> TeachingEvidenceContext:
    artifact = None
    if raw["artifact"]:
        artifact = OpaqueWaveformEvidence(
            reference=ArtifactReference(
                artifact_id=UUID("11111111-1111-4111-8111-111111111111"),
                uri="memory://recorded/pwm-out",
                media_type="application/vnd.aia.waveform+binary",
                size_bytes=2400,
            ),
            channel=raw["measurement_channel"],
            point_count=1200,
            sample_interval_seconds=1e-7,
            time_range_seconds=(-0.00006, 0.00006),
            voltage_range_v=(0.0, 3.3),
            acquisition_mode="recorded",
            captured_at=NOW + timedelta(seconds=2),
        )
    facts = tuple(_evidence_item(item, TeachingEvidenceKind.FACT) for item in raw["facts"])
    analyses = tuple(_evidence_item(item, TeachingEvidenceKind.ANALYSIS) for item in raw["analyses"])
    coherence = raw["coherence"]
    return TeachingEvidenceContext(
        requested_goal="Recorded provider-neutral measurement fixture",
        measurement_decision_reason="Fixture exercises deterministic evidence orchestration.",
        operation="recorded.measurement",
        execution_status=ExecutionStatus.COMPLETED,
        confirmation_state=ConfirmationState.CONFIRMED,
        required_user_action=RequiredUserAction.NONE,
        instrument=InstrumentEvidenceSummary("RECORDED", "FIXTURE", "REDACTED", "fixture-v1"),
        facts=facts,
        analyses=analyses,
        inferences=(),
        quality="degraded" if any(item.quality is EvidenceQuality.UNAVAILABLE for item in facts + analyses) else "good",
        warnings=tuple(raw["warnings"]),
        coherence=None if coherence is None else EvidenceCoherence(coherence["software_observations"], coherence["instrument_vs_software"]),
        artifact=artifact,
        limitations=("Recorded/fake inputs only; no live execution occurred.",),
        failure=None,
        allowed_inference_boundary="No causal diagnosis.",
    )


def _evidence_item(raw, kind: TeachingEvidenceKind) -> TeachingEvidenceItem:
    value = raw["value"]
    if isinstance(value, dict):
        value = DutyCycle.from_ratio(value["ratio"])
    source = TeachingEvidenceSource.INSTRUMENT if kind is TeachingEvidenceKind.FACT else TeachingEvidenceSource.SOFTWARE_ANALYSIS
    return TeachingEvidenceItem(
        kind=kind,
        label=raw["label"],
        value=value,
        unit=raw["unit"],
        source=source,
        quality=EvidenceQuality(raw["quality"]),
        warnings=(),
        provenance=TeachingEvidenceProvenance(
            method="recorded fixture",
            observed_at=NOW + timedelta(seconds=2),
            analysis_algorithm=None if kind is TeachingEvidenceKind.FACT else "recorded-analysis-v1",
            evidence_artifact_ids=(),
        ),
    )
