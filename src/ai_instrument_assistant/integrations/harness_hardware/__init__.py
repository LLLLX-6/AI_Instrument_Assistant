"""Provider-neutral contract semantics for the DeepSeek Harness boundary."""

from .protocol_semantics import (
    ADAPTER_FAILURE_CODES,
    ALLOWED_OPERATIONS,
    MAX_MESSAGE_BYTES,
    CancellationState,
    DeliveryState,
    IndeterminateExecutionError,
    MessageSizeError,
    PendingRequest,
    ProtocolContractState,
    ProtocolSemanticError,
)

__all__ = [
    "ADAPTER_FAILURE_CODES",
    "ALLOWED_OPERATIONS",
    "MAX_MESSAGE_BYTES",
    "CancellationState",
    "DeliveryState",
    "IndeterminateExecutionError",
    "MessageSizeError",
    "PendingRequest",
    "ProtocolContractState",
    "ProtocolSemanticError",
]
