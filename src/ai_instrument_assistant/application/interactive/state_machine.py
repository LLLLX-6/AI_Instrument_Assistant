from __future__ import annotations

from .errors import IllegalWorkflowTransitionError
from .models import WorkflowState


_LINEAR: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.IDLE: frozenset({WorkflowState.OBSERVING_DESIGN}),
    WorkflowState.OBSERVING_DESIGN: frozenset({WorkflowState.DESIGN_CONTEXT_READY}),
    WorkflowState.DESIGN_CONTEXT_READY: frozenset({
        WorkflowState.WAITING_FOR_DESIGN_SELECTION,
        WorkflowState.TARGET_RESOLVED,
    }),
    WorkflowState.WAITING_FOR_DESIGN_SELECTION: frozenset({
        WorkflowState.DESIGN_CONTEXT_READY,
        WorkflowState.TARGET_RESOLVED,
    }),
    WorkflowState.TARGET_RESOLVED: frozenset({WorkflowState.OPERATION_PREPARED}),
    WorkflowState.OPERATION_PREPARED: frozenset({WorkflowState.WAITING_FOR_OPERATION_AUTHORIZATION}),
    WorkflowState.WAITING_FOR_OPERATION_AUTHORIZATION: frozenset({
        WorkflowState.OPERATION_PREPARED,
        WorkflowState.WAITING_FOR_PHYSICAL_CONFIRMATION,
        WorkflowState.READY_TO_EXECUTE,
    }),
    WorkflowState.WAITING_FOR_PHYSICAL_CONFIRMATION: frozenset({
        WorkflowState.OPERATION_PREPARED,
        WorkflowState.READY_TO_EXECUTE,
    }),
    WorkflowState.READY_TO_EXECUTE: frozenset({WorkflowState.CONNECTING_INSTRUMENT}),
    WorkflowState.CONNECTING_INSTRUMENT: frozenset({WorkflowState.MEASURING}),
    WorkflowState.MEASURING: frozenset({WorkflowState.ANALYZING}),
    WorkflowState.ANALYZING: frozenset({WorkflowState.BUILDING_EVIDENCE}),
    WorkflowState.BUILDING_EVIDENCE: frozenset({WorkflowState.GENERATING_TEACHING_RESPONSE}),
    WorkflowState.GENERATING_TEACHING_RESPONSE: frozenset({WorkflowState.COMPLETE}),
    WorkflowState.COMPLETE: frozenset(),
    WorkflowState.FAILED: frozenset(),
    WorkflowState.CANCELLED: frozenset(),
}


def transition_allowed(
    source: WorkflowState,
    target: WorkflowState,
    *,
    raise_on_error: bool = False,
) -> bool:
    allowed = (
        not source.terminal
        and (
            target in _LINEAR[source]
            or target in {WorkflowState.FAILED, WorkflowState.CANCELLED}
        )
    )
    if not allowed and raise_on_error:
        raise IllegalWorkflowTransitionError(
            f"workflow transition {source.value} -> {target.value} is not allowed"
        )
    return allowed
