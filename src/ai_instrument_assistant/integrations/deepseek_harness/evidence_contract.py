from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from ...domain.artifacts import ArtifactReference
from ...domain.engineering_evidence import (
    ConfirmationState,
    EvidenceCoherence,
    EvidenceFailure,
    EvidenceQuality,
    ExecutionStatus,
    InstrumentEvidenceSummary,
    OpaqueWaveformEvidence,
    RequiredUserAction,
    TeachingEvidenceContext,
    TeachingEvidenceItem,
    TeachingEvidenceKind,
    TeachingEvidenceProvenance,
    TeachingEvidenceSource,
)
from ...domain.values import DutyCycle
from ...protocol.schema_registry import SchemaRegistry
from ...protocol.schema_validator import SchemaValidator


EVIDENCE_CONTEXT_SCHEMA_ID = (
    "https://aia.local/protocols/evidence/v1/teaching-evidence-context.schema.json"
)


class EvidenceContractBinding:
    """Schema-first adapter between Evidence v1 wire data and immutable models."""

    schema_id = EVIDENCE_CONTEXT_SCHEMA_ID

    def __init__(self, validator: SchemaValidator) -> None:
        self.validator = validator

    @classmethod
    def from_repository(cls, repository_root: Path) -> EvidenceContractBinding:
        evidence_root = repository_root / "protocols" / "evidence" / "v1"
        hardware_schema = (
            repository_root
            / "protocols"
            / "hardware"
            / "v1"
            / "hardware-tool.schema.json"
        )
        paths = [*sorted(evidence_root.rglob("*.schema.json")), hardware_schema]
        return cls(
            SchemaValidator(
                SchemaRegistry.from_files(paths),
                enforce_formats=True,
            )
        )

    def parse_teaching_context(self, instance: Mapping[str, Any]) -> TeachingEvidenceContext:
        validated = self.validator.validate_and_freeze(self.schema_id, instance)
        data = validated.instance
        return TeachingEvidenceContext(
            requested_goal=data["requestedGoal"],
            measurement_decision_reason=data["measurementDecisionReason"],
            operation=data["operation"],
            execution_status=ExecutionStatus(data["executionStatus"]),
            confirmation_state=ConfirmationState(data["confirmationState"]),
            required_user_action=RequiredUserAction(data["requiredUserAction"]),
            instrument=_instrument_from_wire(data["instrument"]),
            facts=tuple(_item_from_wire(item) for item in data["facts"]),
            analyses=tuple(_item_from_wire(item) for item in data["analyses"]),
            inferences=tuple(_item_from_wire(item) for item in data["inferences"]),
            quality=data["quality"],
            warnings=tuple(data["warnings"]),
            coherence=_coherence_from_wire(data["coherence"]),
            artifact=_artifact_from_wire(data["artifact"]),
            limitations=tuple(data["limitations"]),
            failure=_failure_from_wire(data["failure"]),
            allowed_inference_boundary=data["allowedInferenceBoundary"],
        )

    def to_wire(self, context: TeachingEvidenceContext) -> dict[str, Any]:
        result: dict[str, Any] = {
            "requestedGoal": context.requested_goal,
            "measurementDecisionReason": context.measurement_decision_reason,
            "operation": context.operation,
            "executionStatus": context.execution_status.value,
            "confirmationState": context.confirmation_state.value,
            "requiredUserAction": context.required_user_action.value,
            "instrument": _instrument_to_wire(context.instrument),
            "facts": [_item_to_wire(item) for item in context.facts],
            "analyses": [_item_to_wire(item) for item in context.analyses],
            "inferences": [_item_to_wire(item) for item in context.inferences],
            "quality": context.quality,
            "warnings": list(context.warnings),
            "coherence": _coherence_to_wire(context.coherence),
            "artifact": _artifact_to_wire(context.artifact),
            "limitations": list(context.limitations),
            "failure": _failure_to_wire(context.failure),
            "allowedInferenceBoundary": context.allowed_inference_boundary,
        }
        self.validator.validate_and_freeze(self.schema_id, result)
        return result


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _item_from_wire(data) -> TeachingEvidenceItem:
    value = data["value"]
    if isinstance(value, Mapping):
        duty = DutyCycle.from_ratio(value["ratio"])
        if abs(duty.percent - float(value["percent"])) > 1e-12:
            raise ValueError("duty-cycle ratio and percent representations disagree")
        value = duty
    provenance = data["provenance"]
    return TeachingEvidenceItem(
        kind=TeachingEvidenceKind(data["kind"]),
        label=data["label"],
        value=value,
        unit=data["unit"],
        source=TeachingEvidenceSource(data["source"]),
        quality=EvidenceQuality(data["quality"]),
        warnings=tuple(data["warnings"]),
        provenance=TeachingEvidenceProvenance(
            method=provenance["method"],
            observed_at=_parse_time(provenance["observedAt"]),
            analysis_algorithm=provenance["analysisAlgorithm"],
            evidence_artifact_ids=tuple(UUID(item) for item in provenance["evidenceArtifactIds"]),
        ),
    )


def _item_to_wire(item: TeachingEvidenceItem) -> dict[str, Any]:
    value: Any = item.value
    if isinstance(value, DutyCycle):
        value = {"ratio": value.ratio, "percent": value.percent}
    return {
        "kind": item.kind.value,
        "label": item.label,
        "value": value,
        "unit": item.unit,
        "source": item.source.value,
        "quality": item.quality.value,
        "warnings": list(item.warnings),
        "provenance": {
            "method": item.provenance.method,
            "observedAt": _format_time(item.provenance.observed_at),
            "analysisAlgorithm": item.provenance.analysis_algorithm,
            "evidenceArtifactIds": [str(value) for value in item.provenance.evidence_artifact_ids],
        },
    }


def _instrument_from_wire(data) -> InstrumentEvidenceSummary | None:
    if data is None:
        return None
    return InstrumentEvidenceSummary(
        manufacturer=data["manufacturer"], model=data["model"],
        serial_number=data["serialNumber"], firmware_version=data["firmwareVersion"],
    )


def _instrument_to_wire(value: InstrumentEvidenceSummary | None):
    if value is None:
        return None
    return {"manufacturer": value.manufacturer, "model": value.model, "serialNumber": value.serial_number, "firmwareVersion": value.firmware_version}


def _coherence_from_wire(data) -> EvidenceCoherence | None:
    if data is None:
        return None
    return EvidenceCoherence(data["software_observations"], data["instrument_vs_software"])


def _coherence_to_wire(value: EvidenceCoherence | None):
    if value is None:
        return None
    return {"software_observations": value.software_observations, "instrument_vs_software": value.instrument_vs_software}


def _artifact_from_wire(data) -> OpaqueWaveformEvidence | None:
    if data is None:
        return None
    reference = data["reference"]
    return OpaqueWaveformEvidence(
        reference=ArtifactReference(
            artifact_id=UUID(reference["artifact_id"]), uri=reference["uri"],
            media_type=reference["media_type"], size_bytes=reference.get("size_bytes"),
            sha256=reference.get("sha256"),
        ),
        channel=data["channel"], point_count=data["pointCount"],
        sample_interval_seconds=data["sampleIntervalSeconds"],
        time_range_seconds=tuple(data["timeRangeSeconds"]),
        voltage_range_v=tuple(data["voltageRangeV"]),
        acquisition_mode=data["acquisitionMode"], captured_at=_parse_time(data["capturedAt"]),
        opaque=data["opaque"],
    )


def _artifact_to_wire(value: OpaqueWaveformEvidence | None):
    if value is None:
        return None
    ref = value.reference
    reference = {"artifact_id": str(ref.artifact_id), "uri": ref.uri, "media_type": ref.media_type}
    if ref.size_bytes is not None:
        reference["size_bytes"] = ref.size_bytes
    if ref.sha256 is not None:
        reference["sha256"] = ref.sha256
    return {
        "reference": reference,
        "channel": value.channel, "pointCount": value.point_count,
        "sampleIntervalSeconds": value.sample_interval_seconds,
        "timeRangeSeconds": list(value.time_range_seconds), "voltageRangeV": list(value.voltage_range_v),
        "acquisitionMode": value.acquisition_mode, "capturedAt": _format_time(value.captured_at), "opaque": True,
    }


def _failure_from_wire(data) -> EvidenceFailure | None:
    if data is None:
        return None
    return EvidenceFailure(data["code"], data["message"], data["deliveryState"])


def _failure_to_wire(value: EvidenceFailure | None):
    if value is None:
        return None
    return {"code": value.code, "message": value.message, "deliveryState": value.delivery_state}
