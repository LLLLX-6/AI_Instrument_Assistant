from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from .models import ConnectionState, HardwareState, HostState, WorkflowSession


class ProductErrorCode(StrEnum):
    AMBIGUOUS_SELECTION = "ambiguous_selection"
    DESIGN_OBSERVATION_STALE = "design_observation_stale"
    OPERATION_AUTHORIZATION_REQUIRED = "operation_authorization_required"
    PHYSICAL_CONFIRMATION_REQUIRED = "physical_confirmation_required"
    PHYSICAL_CONFIRMATION_STALE = "physical_confirmation_stale"
    INSTRUMENT_NOT_CONNECTED = "instrument_not_connected"
    INSTRUMENT_DISCONNECTED = "instrument_disconnected"
    MODEL_CANDIDATE_INVALID = "model_candidate_invalid"
    FALLBACK_PUBLISHED = "fallback_published"
    VERSION_INCOMPATIBLE = "version_incompatible"
    LOCAL_PORT_IN_USE = "local_port_in_use"


PRODUCT_ERROR_MESSAGES = MappingProxyType({
    ProductErrorCode.AMBIGUOUS_SELECTION: "Choose the intended design object to continue.",
    ProductErrorCode.DESIGN_OBSERVATION_STALE: "The design changed; refresh the selection.",
    ProductErrorCode.OPERATION_AUTHORIZATION_REQUIRED: "Review the requested measurement operations.",
    ProductErrorCode.PHYSICAL_CONFIRMATION_REQUIRED: "Confirm the displayed probe setup before measurement.",
    ProductErrorCode.PHYSICAL_CONFIRMATION_STALE: "The measurement setup changed; confirm it again.",
    ProductErrorCode.INSTRUMENT_NOT_CONNECTED: "The instrument is not connected.",
    ProductErrorCode.INSTRUMENT_DISCONNECTED: "The instrument connection was lost.",
    ProductErrorCode.MODEL_CANDIDATE_INVALID: "The generated candidate could not be published safely.",
    ProductErrorCode.FALLBACK_PUBLISHED: "A deterministic evidence-based result was published.",
    ProductErrorCode.VERSION_INCOMPATIBLE: "The connected component version is incompatible.",
    ProductErrorCode.LOCAL_PORT_IN_USE: "The local application endpoint is already in use.",
})


@dataclass(frozen=True, slots=True)
class ProductStatus:
    host_state: HostState
    protocol_compatible: bool
    harness_state: ConnectionState
    jlceda_state: ConnectionState
    hardware_state: HardwareState
    workflow_state: str | None
    workflow_revision: int | None
    safe_workflow_label: str | None
    last_error_code: ProductErrorCode | None
    message: str


def project_product_status(
    *,
    host_state: HostState,
    protocol_compatible: bool,
    harness_connected: bool,
    jlceda_connected: bool,
    hardware_state: HardwareState,
    workflow: WorkflowSession | None,
    last_error_code: ProductErrorCode | None = None,
    message: str | None = None,
) -> ProductStatus:
    safe_message = safe_message_for(last_error_code) if message is None else _safe_text(message, 256)
    return ProductStatus(
        host_state=host_state,
        protocol_compatible=bool(protocol_compatible),
        harness_state=ConnectionState.CONNECTED if harness_connected else ConnectionState.DISCONNECTED,
        jlceda_state=ConnectionState.CONNECTED if jlceda_connected else ConnectionState.DISCONNECTED,
        hardware_state=hardware_state,
        workflow_state=None if workflow is None else workflow.state.value,
        workflow_revision=None if workflow is None else workflow.revision,
        safe_workflow_label=None if workflow is None else _safe_text(workflow.safe_label, 80),
        last_error_code=last_error_code,
        message=safe_message,
    )


def safe_message_for(error_code: ProductErrorCode | None) -> str:
    """Map a stable product code to approved user-visible text."""
    if error_code is None:
        return "AI Instrument Assistant is ready."
    if not isinstance(error_code, ProductErrorCode):
        raise TypeError("error_code must be ProductErrorCode or None")
    return PRODUCT_ERROR_MESSAGES[error_code]


def _safe_text(value: object, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("safe product text must be non-empty")
    text = " ".join(value.split())
    if len(text) > maximum:
        text = text[:maximum]
    return text
