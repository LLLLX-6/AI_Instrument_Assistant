from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    FrontendKind,
    InteractiveApplicationError,
    WorkflowState,
)
from ai_instrument_assistant.application.ports.eda_interface import (
    EDAInterface,
    EDAInterfaceError,
    GuardMode,
    HighlightCommand,
    HighlightResult,
)
from ai_instrument_assistant.application.services.eda_design_evidence import (
    DesignEvidenceProjection,
    EDADesignEvidenceCaptureService,
)
from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    build_candidate_set_binding,
)
from ai_instrument_assistant.domain.eda.models import DesignObjectRef


class DesignObservationStatus(StrEnum):
    COMMITTED = "COMMITTED"
    STALE = "STALE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class DesignObservationActionResult:
    status: DesignObservationStatus
    code: str
    workflow_revision: int | None


class InteractiveActionUnavailableError(InteractiveApplicationError):
    """A bounded product action is not composed in the current runtime."""

    code = "host_unavailable"


class ProductionInteractiveApplicationActions:
    """Thin async adapter from interactive intent to existing application services."""

    def __init__(self, *, host: ApplicationHost, eda: EDAInterface) -> None:
        self._host = host
        self._eda = eda
        self._capture = EDADesignEvidenceCaptureService(eda=eda)
        self._observations: dict[UUID, DesignEvidenceProjection] = {}

    async def request_design_observation(
        self,
        workflow_id: UUID,
        expected_revision: int,
    ) -> DesignObservationActionResult:
        guard = self._host.capture_workflow_guard(workflow_id, expected_revision)
        try:
            projection = await self._capture.capture()
        except (EDAInterfaceError, TimeoutError):
            failed = self._host.fail_guarded_workflow(
                guard,
                code="design_observation_unavailable",
                message="The current design observation is unavailable.",
            )
            if failed is None:
                return DesignObservationActionResult(
                    DesignObservationStatus.STALE,
                    "design_observation_stale",
                    None,
                )
            return DesignObservationActionResult(
                DesignObservationStatus.FAILED,
                "design_observation_unavailable",
                failed.revision,
            )

        observation_identity = _observation_identity(projection)
        selection_context = projection.design_context.selection
        if selection_context is None:
            raise InteractiveActionUnavailableError(
                "current design selection is unavailable"
            )
        selected = selection_context.selection.selected_objects
        candidate_binding = None
        if len(selected) >= 2 and selection_context.selection.primary_object is None:
            candidate_binding = build_candidate_set_binding(
                selection_context=selection_context,
                selection_observed_at=projection.design_context.evidence[0].observed_at,
            )
        committed = self._host.commit_guarded_design_observation(
            guard,
            observation_identity,
            selection_context=selection_context,
            candidate_binding=candidate_binding,
            probe_target=projection.probe_target,
        )
        if committed is None:
            return DesignObservationActionResult(
                DesignObservationStatus.STALE,
                "design_observation_stale",
                None,
            )
        self._observations[workflow_id] = projection
        final_revision = committed.revision
        if candidate_binding is not None:
            challenge = self._host.request_design_selection(
                workflow_id,
                committed.revision,
                FrontendKind.JLCEDA,
                timedelta(minutes=2),
            )
            final_revision = challenge.workflow_revision
        elif projection.probe_target is not None:
            resolved = self._host.transition(
                workflow_id,
                committed.revision,
                WorkflowState.TARGET_RESOLVED,
            )
            final_revision = resolved.revision
        return DesignObservationActionResult(
            DesignObservationStatus.COMMITTED,
            "design_observation_committed",
            final_revision,
        )

    async def prepare_measurement(
        self,
        workflow_id: UUID,
        expected_revision: int,
        payload: object,
    ) -> object:
        del workflow_id, expected_revision, payload
        raise InteractiveActionUnavailableError(
            "measurement preparation is not composed in Phase 8.5B"
        )

    async def highlight_target(
        self,
        workflow_id: UUID,
        expected_revision: int,
    ) -> HighlightResult:
        self._host.capture_workflow_guard(workflow_id, expected_revision)
        retained = self._observations.get(workflow_id)
        workflow = self._host.get_workflow(workflow_id)
        if retained is None:
            raise InteractiveActionUnavailableError("current design target is unavailable")
        projection = retained
        target = workflow.probe_target
        if target is None:
            raise InteractiveActionUnavailableError("current design target is unavailable")
        if workflow.design_observation_ref != _observation_identity(projection):
            raise InteractiveActionUnavailableError("current design target is unavailable")
        document = projection.design_context.document
        command_identity = _content_identity({
            "scope": "interactive-highlight-command/v1",
            "workflow_id": str(workflow_id),
            "workflow_revision": expected_revision,
            "target": _ref_payload(target.design_object),
        })
        return await self._eda.highlight(HighlightCommand(
            document_ref=document.document_ref,
            expected_snapshot_id=document.snapshot_id,
            expected_fingerprint=document.fingerprint,
            targets=(target.design_object,),
            idempotency_key=command_identity,
            guard_mode=GuardMode.WEAK_IDENTITY_CHECK,
            allow_scope_expansion=True,
        ))

    async def request_teaching_publication(
        self,
        workflow_id: UUID,
        expected_revision: int,
    ) -> object:
        del workflow_id, expected_revision
        raise InteractiveActionUnavailableError(
            "teaching publication is not composed in Phase 8.5B"
        )


def _observation_identity(projection: DesignEvidenceProjection) -> str:
    context = projection.design_context.selection
    return _content_identity({
        "scope": "interactive-design-observation/v1",
        "document": _ref_payload(context.selection.document_ref),
        "selected": [_ref_payload(value) for value in context.selection.selected_objects],
        "nets": [_ref_payload(value.ref) for value in context.nets],
    })


def _ref_payload(value: DesignObjectRef) -> dict[str, str]:
    return {
        "provider": value.provider,
        "document_id": value.document_id,
        "snapshot_id": str(value.snapshot_id),
        "object_type": value.object_type.value,
        "canonical_id": value.canonical_id,
    }


def _content_identity(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
