from __future__ import annotations

from uuid import uuid4

from ai_instrument_assistant.application.interactive.errors import ChallengeRejectedError
from ai_instrument_assistant.application.interactive.models import (
    ValidatedDesignSelectionRequest,
)
from ai_instrument_assistant.application.services import design_selection_disambiguation
from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    TrustedDesignSelectionResolution,
    TrustedDesignSelectionResolutionStatus,
)


class ProductionDesignSelectionDecisionIssuer:
    """Thin Python adapter to the reviewed trusted design-selection authority."""

    def issue_design_selection(
        self,
        request: ValidatedDesignSelectionRequest,
    ) -> TrustedDesignSelectionResolution:
        if not isinstance(request, ValidatedDesignSelectionRequest):
            raise TypeError("validated design-selection request is required")
        decision = design_selection_disambiguation.issue_trusted_design_selection_decision(
            decision_id=uuid4(),
            candidate_binding=request.candidate_binding,
            selected_candidate=request.selected_candidate,
            workflow_id=str(request.workflow_id),
            request_correlation_id=request.request_correlation_id,
            decided_at=request.decided_at,
        )
        resolution = design_selection_disambiguation.resolve_trusted_design_selection(
            current_selection=request.selection_context,
            current_binding=request.candidate_binding,
            decision=decision,
            trusted_workflow_id=str(request.workflow_id),
            trusted_request_correlation_id=request.request_correlation_id,
        )
        if resolution.status is not TrustedDesignSelectionResolutionStatus.RESOLVED:
            raise ChallengeRejectedError("trusted design selection could not be resolved")
        return resolution
