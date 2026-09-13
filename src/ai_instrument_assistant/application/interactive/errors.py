"""Bounded errors for the interactive application boundary."""


class InteractiveApplicationError(RuntimeError):
    """Base error with a stable product code."""

    code = "invalid_command"


class WorkflowNotFoundError(InteractiveApplicationError):
    code = "invalid_command"


class StaleWorkflowRevisionError(InteractiveApplicationError):
    code = "stale_workflow_revision"


class IllegalWorkflowTransitionError(InteractiveApplicationError):
    code = "invalid_command"


class ChallengeRejectedError(InteractiveApplicationError):
    code = "challenge_rejected"


class FrontendConnectionError(InteractiveApplicationError):
    code = "invalid_command"


class InteractiveCapabilityUnavailableError(InteractiveApplicationError):
    code = "host_unavailable"


class InvalidEventCursorError(InteractiveApplicationError):
    code = "invalid_command"
