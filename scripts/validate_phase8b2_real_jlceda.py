from __future__ import annotations

import argparse
import asyncio
import json
import string
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_instrument_assistant.application.services.eda_design_evidence import (
    DesignEvidenceProjection,
    DesignEvidenceProjectionStatus,
    EDADesignEvidenceCaptureService,
    SelectionProjectionDiagnostic,
    create_user_provided_numeric_target,
    diagnose_selection_projection,
)
from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    DesignSelectionCandidateIdentity,
    DesignSelectionCandidateSetBinding,
    TrustedDesignSelectionDecision,
    TrustedDesignSelectionResolutionStatus,
    build_candidate_set_binding,
    candidate_choice_tokens,
    issue_trusted_design_selection_decision,
    resolve_trusted_design_selection,
)
from ai_instrument_assistant.application.services.engineering_evidence import (
    DeterministicEngineeringComparator,
    EngineeringEvidenceAssembler,
)
from ai_instrument_assistant.application.services.engineering_evidence_workflow import (
    EngineeringEvidenceWorkflow,
    EngineeringEvidenceWorkflowRequest,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    ComparisonStatus,
    CrossReferenceState,
    DesignEvidenceContext,
    EngineeringMetric,
    RelativeTolerance,
    TrustedPhysicalConfirmationEvidence,
)
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.remote_adapter import JLCEDARemoteAdapter
from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.evidence_binding import EvidenceContractBinding
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator

from scripts.run_jlceda_gateway import (
    DEFAULT_SECRET_PATH,
    PROTOCOL_ROOT,
    load_secret,
    stable_port,
)


WORKFLOW_ID = "phase8b2-real-jlceda-recorded"
REQUEST_ID = "phase8b2-request-1"
MEASUREMENT_CONTEXT_ID = UUID("51515151-5151-4151-8151-515151515151")
WORKFLOW_CONTEXT_ID = UUID("66666666-6666-4666-8666-666666666666")
FREQUENCY_EVIDENCE_ID = UUID("62626262-6262-4262-8262-626262626262")
FREQUENCY_TARGET_ID = UUID("63636363-6363-4363-8363-636363636363")
DUTY_EVIDENCE_ID = UUID("64646464-6464-4464-8464-646464646464")
DUTY_TARGET_ID = UUID("65656565-6565-4565-8565-656565656565")
TOLERANCE_EVIDENCE_ID = UUID("67676767-6767-4767-8767-676767676767")
TOLERANCE_TARGET_ID = UUID("68686868-6868-4868-8868-686868686868")
RECORDED_EVIDENCE = (
    REPOSITORY_ROOT
    / "protocols"
    / "evidence"
    / "v1"
    / "fixtures"
    / "valid"
    / "pwm-teaching-context.case.json"
)


@dataclass(frozen=True, slots=True)
class BoundedValidationFailure(Exception):
    stage: str
    code: str
    diagnostic: SelectionProjectionDiagnostic | None = None

    def output(self) -> dict[str, object]:
        output: dict[str, object] = {
            "status": "NOT_PASS",
            "failure": {"stage": self.stage, "code": self.code},
            "fixture_fallback_used": False,
            "automatic_retry_count": 0,
            "hardware_execution_count": 0,
            "model_request_count": 0,
        }
        if self.diagnostic is not None:
            output["diagnostic"] = _selection_diagnostic_summary(self.diagnostic)
        return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate real read-only JLCEDA design evidence against recorded hardware evidence"
        )
    )
    parser.add_argument("--port", type=stable_port, default=49624)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--connect-timeout", type=float, default=45.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    return parser.parse_args()


async def run_real(args: argparse.Namespace) -> dict[str, object]:
    if args.connect_timeout <= 0 or args.request_timeout <= 0:
        raise BoundedValidationFailure("connection", "invalid_timeout")
    try:
        secret = load_secret(args.secret_file.resolve())
    except Exception as error:
        raise BoundedValidationFailure("authentication", "secret_unavailable") from error

    validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL_ROOT))
    gateway = LocalWebSocketGateway(
        validator=validator,
        state_machine=ProtocolStateMachine(secret=secret),
    )
    try:
        try:
            await gateway.start(port=args.port)
        except Exception as error:
            raise BoundedValidationFailure("connection", "gateway_start_failed") from error
        print(
            "Phase 8B.2 gateway ready; keep JLCEDA on the schematic and select one PWM_OUT wire.",
            file=sys.stderr,
        )
        await _wait_for_authenticated_extension(gateway, args.connect_timeout)
        adapter = JLCEDARemoteAdapter(
            request_client=gateway,
            validator=validator,
            mapper=JLCEDADomainMapper(),
            request_timeout=args.request_timeout,
        )
        try:
            active_document = await adapter.get_active_document()
        except Exception as error:
            raise BoundedValidationFailure("active_document", "read_failed") from error
        try:
            selection = await adapter.get_selection()
        except Exception as error:
            raise BoundedValidationFailure("selection", "read_failed") from error
        try:
            observed_at = datetime.now(timezone.utc)
            projection = EDADesignEvidenceCaptureService(
                eda=adapter,
                clock=lambda: datetime.now(timezone.utc),
            ).project(
                active_document=active_document,
                selection_context=selection,
                observed_at=observed_at,
            )
        except Exception as error:
            raise BoundedValidationFailure("projection", "projection_failed") from error
        if projection.status is DesignEvidenceProjectionStatus.AMBIGUOUS_SELECTION:
            diagnostic = diagnose_selection_projection(selection)
            try:
                candidate_binding = build_candidate_set_binding(
                    selection_context=selection,
                    selection_observed_at=observed_at,
                )
                trusted_decision = await _prompt_for_trusted_selection_decision(
                    candidate_binding
                )
                resolution = resolve_trusted_design_selection(
                    current_selection=selection,
                    current_binding=candidate_binding,
                    decision=trusted_decision,
                    trusted_workflow_id=WORKFLOW_ID,
                    trusted_request_correlation_id=REQUEST_ID,
                )
            except BoundedValidationFailure:
                raise
            except Exception as error:
                raise BoundedValidationFailure(
                    "disambiguation",
                    "decision_failed",
                    diagnostic,
                ) from error
            if resolution.status is not TrustedDesignSelectionResolutionStatus.RESOLVED:
                raise BoundedValidationFailure(
                    "disambiguation",
                    resolution.reason.value.lower(),
                    diagnostic,
                )
            try:
                projection = EDADesignEvidenceCaptureService.project(
                    active_document=active_document,
                    selection_context=selection,
                    observed_at=observed_at,
                    trusted_resolution=resolution,
                )
            except Exception as error:
                raise BoundedValidationFailure(
                    "projection",
                    "trusted_resolution_projection_failed",
                    diagnostic,
                ) from error
        if projection.status is not DesignEvidenceProjectionStatus.PROJECTED:
            raise BoundedValidationFailure(
                "projection",
                projection.status.value.lower(),
                diagnose_selection_projection(selection),
            )
        try:
            return execute_recorded_workflow(
                projection=projection,
                assembled_at=datetime.now(timezone.utc),
            )
        except BoundedValidationFailure:
            raise
        except Exception as error:
            raise BoundedValidationFailure("workflow", "execution_failed") from error
    finally:
        await gateway.stop()


async def _wait_for_authenticated_extension(
    gateway: LocalWebSocketGateway,
    timeout: float,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while gateway.authenticated_session_count != 1:
        if asyncio.get_running_loop().time() >= deadline:
            stage = "authentication" if gateway.active_connection_count else "connection"
            raise BoundedValidationFailure(stage, "extension_not_authenticated")
        await asyncio.sleep(0.1)


def create_cli_trusted_selection_decision(
    *,
    candidate_binding: DesignSelectionCandidateSetBinding,
    menu_choice: str,
    decided_at: datetime,
    decision_id: UUID,
) -> TrustedDesignSelectionDecision:
    """Map one exact bounded menu key to an opaque current candidate identity."""

    options = candidate_choice_tokens(candidate_binding)
    if len(options) > len(string.ascii_uppercase):
        raise BoundedValidationFailure("disambiguation", "candidate_menu_too_large")
    if not isinstance(menu_choice, str):
        raise BoundedValidationFailure("disambiguation", "invalid_menu_choice")
    normalized = menu_choice.strip().upper()
    allowed = {
        string.ascii_uppercase[index]: identity
        for index, (_, identity) in enumerate(options)
    }
    selected = allowed.get(normalized)
    if selected is None:
        raise BoundedValidationFailure("disambiguation", "invalid_menu_choice")
    try:
        return issue_trusted_design_selection_decision(
            decision_id=decision_id,
            candidate_binding=candidate_binding,
            selected_candidate=selected,
            workflow_id=WORKFLOW_ID,
            request_correlation_id=REQUEST_ID,
            decided_at=decided_at,
        )
    except Exception as error:
        raise BoundedValidationFailure("disambiguation", "decision_rejected") from error


async def _prompt_for_trusted_selection_decision(
    candidate_binding: DesignSelectionCandidateSetBinding,
) -> TrustedDesignSelectionDecision:
    options = candidate_choice_tokens(candidate_binding)
    if len(options) > len(string.ascii_uppercase):
        raise BoundedValidationFailure("disambiguation", "candidate_menu_too_large")
    print("Multiple bounded design objects were observed:", file=sys.stderr)
    for index, candidate in enumerate(candidate_binding.presented_candidates):
        key = string.ascii_uppercase[index]
        kind = candidate.provider_kind or candidate.object_type.value
        label = candidate.display_name or "unavailable"
        print(f"  {key}. {kind} — {label}", file=sys.stderr)
    choice = await asyncio.to_thread(
        input,
        "Choose the exact design object to use for this workflow: ",
    )
    return create_cli_trusted_selection_decision(
        candidate_binding=candidate_binding,
        menu_choice=choice,
        decided_at=datetime.now(timezone.utc),
        decision_id=uuid4(),
    )


def execute_recorded_workflow(
    *,
    projection: DesignEvidenceProjection,
    assembled_at: datetime,
) -> dict[str, object]:
    if projection.probe_target is None:
        raise BoundedValidationFailure("projection", "probe_target_missing")
    recorded = _load_recorded_evidence()
    measured_at = max(
        item.provenance.observed_at for item in (*recorded.facts, *recorded.analyses)
    )
    confirmed_at = measured_at - timedelta(seconds=1)
    frequency = create_user_provided_numeric_target(
        evidence_id=FREQUENCY_EVIDENCE_ID,
        target_id=FREQUENCY_TARGET_ID,
        document=projection.design_context.document,
        design_object=projection.probe_target.design_object,
        observed_at=confirmed_at,
        label="PWM_OUT expected frequency from trusted user context",
        metric=EngineeringMetric.FREQUENCY,
        value=10.0,
        unit="kHz",
        tolerance=None,
    )
    duty = create_user_provided_numeric_target(
        evidence_id=DUTY_EVIDENCE_ID,
        target_id=DUTY_TARGET_ID,
        document=projection.design_context.document,
        design_object=projection.probe_target.design_object,
        observed_at=confirmed_at,
        label="PWM_OUT expected duty cycle from trusted user context",
        metric=EngineeringMetric.DUTY_CYCLE,
        value=30.0,
        unit="percent",
        tolerance=None,
    )
    design_context = _with_target_evidence(projection, (frequency.evidence, duty.evidence))
    trusted_confirmation = _confirmation_fixture(projection, confirmed_at)
    workflow = EngineeringEvidenceWorkflow(
        assembler=EngineeringEvidenceAssembler(),
        comparator=DeterministicEngineeringComparator(),
    )
    result = workflow.execute(
        EngineeringEvidenceWorkflowRequest(
            context_id=WORKFLOW_CONTEXT_ID,
            workflow_id=WORKFLOW_ID,
            request_correlation_id=REQUEST_ID,
            user_goal="Compare real JLCEDA PWM_OUT structure with recorded PWM evidence",
            assembled_at=max(assembled_at, measured_at + timedelta(seconds=1)),
            design_context=design_context,
            targets=(frequency.target, duty.target),
            probe_target=projection.probe_target,
            confirmation=trusted_confirmation,
            measurement_context_id=MEASUREMENT_CONTEXT_ID,
            measurement_context=recorded,
            measurement_channel=1,
            measured_at=measured_at,
        )
    )

    tolerance_frequency = create_user_provided_numeric_target(
        evidence_id=TOLERANCE_EVIDENCE_ID,
        target_id=TOLERANCE_TARGET_ID,
        document=projection.design_context.document,
        design_object=projection.probe_target.design_object,
        observed_at=confirmed_at,
        label="PWM_OUT expected frequency with trusted user tolerance",
        metric=EngineeringMetric.FREQUENCY,
        value=10.0,
        unit="kHz",
        tolerance=RelativeTolerance.from_percent(1.0),
    )
    tolerance_result = workflow.execute(
        EngineeringEvidenceWorkflowRequest(
            context_id=UUID("69696969-6969-4969-8969-696969696969"),
            workflow_id=WORKFLOW_ID,
            request_correlation_id=REQUEST_ID,
            user_goal="Apply explicit trusted user tolerance to recorded frequency evidence",
            assembled_at=max(assembled_at, measured_at + timedelta(seconds=1)),
            design_context=_with_target_evidence(
                projection,
                (tolerance_frequency.evidence,),
            ),
            targets=(tolerance_frequency.target,),
            probe_target=projection.probe_target,
            confirmation=trusted_confirmation,
            measurement_context_id=MEASUREMENT_CONTEXT_ID,
            measurement_context=recorded,
            measurement_channel=1,
            measured_at=measured_at,
        )
    )
    _require_expected_results(result, tolerance_result)
    return _bounded_success(projection, result, tolerance_result, measured_at)


def _load_recorded_evidence():
    raw = json.loads(RECORDED_EVIDENCE.read_text(encoding="utf-8"))["instance"]
    return EvidenceContractBinding.from_repository(REPOSITORY_ROOT).parse_teaching_context(raw)


def _with_target_evidence(projection, evidence) -> DesignEvidenceContext:
    current = projection.design_context
    return DesignEvidenceContext(
        document=current.document,
        evidence=current.evidence + tuple(evidence),
        probe_targets=current.probe_targets,
        selection=current.selection,
    )


def _confirmation_fixture(
    projection: DesignEvidenceProjection,
    confirmed_at: datetime,
) -> TrustedPhysicalConfirmationEvidence:
    probe = projection.probe_target
    if probe is None:
        raise BoundedValidationFailure("projection", "probe_target_missing")
    return TrustedPhysicalConfirmationEvidence(
        confirmation_id="phase8b2-trusted-confirmation-fixture",
        source="TRUSTED_USER_EVENT",
        confirmed_by="phase8b2-trusted-fixture",
        workflow_id=WORKFLOW_ID,
        request_correlation_id=REQUEST_ID,
        channel=1,
        target_ref=probe.design_object.canonical_id,
        design_snapshot_id=probe.snapshot_id,
        probe_target_id=probe.target_id,
        safe_low_voltage_confirmed=True,
        common_ground_confirmed=True,
        wiring_unchanged=True,
        confirmed_at=confirmed_at,
    )


def _require_expected_results(result, tolerance_result) -> None:
    links = result.engineering_context.cross_references
    if len(links) != 1 or links[0].state is not CrossReferenceState.VERIFIED_LINK:
        raise BoundedValidationFailure("workflow", "cross_reference_not_verified")
    comparisons = result.engineering_context.comparison_results
    if len(comparisons) != 3 or any(
        item.status is not ComparisonStatus.INDETERMINATE for item in comparisons
    ):
        raise BoundedValidationFailure("workflow", "unexpected_no_tolerance_result")
    tolerance = tolerance_result.engineering_context.comparison_results
    if len(tolerance) != 2 or any(item.status is not ComparisonStatus.MATCH for item in tolerance):
        raise BoundedValidationFailure("workflow", "unexpected_tolerance_result")
    if (
        result.engineering_context.inferences
        or result.teaching_context.inferences
        or result.teaching_context.candidate_next_measurements
    ):
        raise BoundedValidationFailure("workflow", "unexpected_generated_inference")


def _bounded_success(projection, result, tolerance_result, measured_at) -> dict[str, object]:
    active = projection.active_document
    selected = projection.design_context.selection.selection.selected_objects
    probe = projection.probe_target
    engineering = result.engineering_context
    teaching = result.teaching_context
    return {
        "status": "PASS",
        "validation": "phase8b2-real-jlceda-recorded-hardware",
        "real_jlceda": {
            "provider": active.document_ref.provider,
            "document_canonical_id": active.document_ref.canonical_id,
            "document_type": active.document_type,
            "active_document_snapshot_id": str(active.snapshot_id),
            "selection_snapshot_id": str(projection.design_context.document.snapshot_id),
            "selected_objects": [
                {
                    "object_type": item.object_type.value,
                    "canonical_id": item.canonical_id,
                    "display_name": item.display_name,
                    "provider_kind": item.provider_kind,
                }
                for item in selected
            ],
            "provider_primary_object": None
            if projection.design_context.selection.selection.primary_object is None
            else projection.design_context.selection.selection.primary_object.canonical_id,
        },
        "trusted_design_disambiguation": _trusted_disambiguation_summary(projection),
        "provider_neutral_projection": {
            "status": projection.status.value,
            "design_evidence": [
                {
                    "evidence_id": str(item.evidence_id),
                    "kind": item.kind.value,
                    "origin": item.origin.value,
                    "label": item.label,
                    "object_ref": None if item.design_object is None else item.design_object.canonical_id,
                }
                for item in projection.design_context.evidence
            ],
            "probe_target": {
                "target_id": str(probe.target_id),
                "kind": probe.kind.value,
                "design_object_ref": probe.design_object.canonical_id,
                "snapshot_id": str(probe.snapshot_id),
                "physical_confirmation": False,
            },
        },
        "target_provenance": {
            "source": "USER_PROVIDED",
            "frequency": {"value": 10.0, "unit": "kHz", "tolerance": None},
            "duty_cycle": {"value": 30.0, "unit": "percent", "tolerance": None},
            "schematic_derived": False,
        },
        "recorded_hardware_evidence": {
            "measurement_context_id": str(engineering.measurement_context_id),
            "measured_at": measured_at.isoformat(),
            "facts": [_evidence_summary(item) for item in engineering.measurement_context.facts],
            "analyses": [_evidence_summary(item) for item in engineering.measurement_context.analyses],
            "artifact": None
            if engineering.measurement_context.artifact is None
            else {
                "artifact_id": str(engineering.measurement_context.artifact.reference.artifact_id),
                "point_count": engineering.measurement_context.artifact.point_count,
                "opaque": engineering.measurement_context.artifact.opaque,
            },
        },
        "trusted_confirmation_fixture": {
            "confirmation_id": engineering.cross_references[0].confirmation_id,
            "workflow_id": engineering.cross_references[0].workflow_id,
            "request_correlation_id": engineering.cross_references[0].request_correlation_id,
            "channel": engineering.cross_references[0].measurement_channel,
            "design_snapshot_id": str(engineering.cross_references[0].design_snapshot_id),
            "source": engineering.cross_references[0].confirmation_source,
            "real_physical_event": False,
        },
        "cross_reference": {
            "state": engineering.cross_references[0].state.value,
            "reasons": list(engineering.cross_references[0].reasons),
        },
        "comparisons_without_tolerance": [
            _comparison_summary(item) for item in engineering.comparison_results
        ],
        "frequency_comparisons_with_explicit_one_percent_tolerance": [
            _comparison_summary(item)
            for item in tolerance_result.engineering_context.comparison_results
        ],
        "contexts": {
            "engineering_inference_count": len(engineering.inferences),
            "teaching_inference_count": len(teaching.inferences),
            "candidate_next_measurement_count": len(teaching.candidate_next_measurements),
            "assembler": f"{engineering.assembler_name}/{engineering.assembler_version}",
            "comparator": "aia.deterministic-explicit-tolerance/1",
        },
        "external_actions": {
            "jlceda_document_reads": 1,
            "jlceda_selection_reads": 1,
            "jlceda_writes": 0,
            "hardware_backend_starts": 0,
            "hardware_ipc_dispatches": 0,
            "physical_measurements": 0,
            "model_requests": 0,
        },
        "limitations": [
            *projection.limitations,
            (
                "Real JLCEDA supplied structural design evidence. Expected electrical "
                "targets in this validation were supplied as trusted user context and "
                "were not claimed as schematic-derived values."
            ),
            "Hardware evidence is a canonical recorded fixture; no live measurement occurred.",
            "The trusted confirmation is a non-executing validation fixture, not a real event.",
            "Design and recorded measurement observations are not simultaneous or atomic.",
            "No diagnosis or causal inference was generated.",
        ],
    }


def _trusted_disambiguation_summary(
    projection: DesignEvidenceProjection,
) -> dict[str, object] | None:
    resolution = projection.trusted_selection_resolution
    if resolution is None:
        return None
    decision = resolution.decision
    if decision is None or resolution.probe_target is None:
        raise BoundedValidationFailure("disambiguation", "audit_provenance_missing")
    binding = resolution.candidate_binding
    return {
        "status": resolution.status.value,
        "reason": resolution.reason.value,
        "ambiguity_reason": "multiple_selected_objects",
        "provider_primary_object": None,
        "decision_id": str(decision.decision_id),
        "trusted_origin": decision.trusted_origin.value,
        "workflow_id": decision.workflow_id,
        "request_correlation_id": decision.request_correlation_id,
        "document_canonical_id": binding.document_ref.canonical_id,
        "snapshot_id": str(binding.document_ref.snapshot_id),
        "selection_observed_at": binding.selection_observed_at.isoformat(),
        "decided_at": decision.decided_at.isoformat(),
        "fingerprint_scope": binding.fingerprint_scope,
        "candidate_set_fingerprint": binding.candidate_set_fingerprint,
        "candidate_identities": [
            {
                "provider": identity.provider,
                "document_id": identity.document_id,
                "snapshot_id": str(identity.snapshot_id),
                "object_type": identity.object_type.value,
                "canonical_id": identity.canonical_id,
            }
            for identity in binding.candidate_identities
        ],
        "chosen_candidate": {
            "object_type": decision.selected_identity.object_type.value,
            "canonical_id": decision.selected_identity.canonical_id,
        },
        "derived_target": {
            "object_type": resolution.derived_target.object_type.value,
            "canonical_id": resolution.derived_target.canonical_id,
        },
        "probe_target_id": str(resolution.probe_target.target_id),
    }


def _evidence_summary(item) -> dict[str, object]:
    value = item.value
    if hasattr(value, "ratio"):
        value = {"ratio": value.ratio, "percent": value.percent}
    return {
        "label": item.label,
        "value": value,
        "unit": item.unit,
        "source": item.source.value,
        "quality": item.quality.value,
        "observed_at": item.provenance.observed_at.isoformat(),
    }


def _selection_diagnostic_summary(
    diagnostic: SelectionProjectionDiagnostic,
) -> dict[str, object]:
    return {
        "selection_count": diagnostic.selection_count,
        "provider_kinds": list(diagnostic.provider_kinds),
        "selected_objects": [
            {
                "object_type": item.object_type.value,
                "provider_kind": item.provider_kind,
                "native_id": item.native_id,
                "canonical_id": item.canonical_id,
                "display_name": item.display_name,
            }
            for item in diagnostic.selected_references
        ],
        "derived_net_count": diagnostic.derived_net_count,
        "projected_candidate_count": diagnostic.projected_candidate_count,
        "projected_candidate_kinds": [
            kind.value for kind in diagnostic.projected_candidate_kinds
        ],
        "projected_candidate_refs": [
            item.canonical_id for item in diagnostic.projected_candidates
        ],
        "ambiguity_reason": diagnostic.reason.value,
        "resolution_stage": diagnostic.resolution_stage.value,
        "scope_expansion": diagnostic.scope_expansion.value,
    }


def _comparison_summary(item) -> dict[str, object]:
    observed = item.observed
    observed_value = None if observed is None else getattr(observed, "value", observed)
    observed_unit = None if observed is None else getattr(observed, "unit", None)
    return {
        "metric": item.metric.value,
        "observed_label": None if item.observed_ref is None else item.observed_ref.label,
        "observed_category": None
        if item.observed_ref is None
        else item.observed_ref.category.value,
        "observed_value": observed_value,
        "observed_unit": observed_unit,
        "status": item.status.value,
        "reason": item.reason.value,
        "comparator": f"{item.comparator_name}/{item.comparator_version}",
    }


def main() -> int:
    try:
        output = asyncio.run(run_real(parse_args()))
    except KeyboardInterrupt:
        output = BoundedValidationFailure("connection", "cancelled").output()
    except BoundedValidationFailure as error:
        output = error.output()
    except Exception:
        output = BoundedValidationFailure("workflow", "unexpected_failure").output()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
