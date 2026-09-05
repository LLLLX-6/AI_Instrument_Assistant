"""Explicit integration encoder; JSON Schema validates its output before I/O."""
from dataclasses import asdict
from ai_instrument_assistant.application.ports.eda_interface import HighlightCommand
from ai_instrument_assistant.domain.eda.models import DesignObjectRef


def encode_ref(ref: DesignObjectRef) -> dict[str, object]:
    return {
        **asdict(ref), "model_version": "1.0",
        "snapshot_id": str(ref.snapshot_id), "object_type": ref.object_type.value,
    }


def encode_highlight(command: HighlightCommand) -> dict[str, object]:
    fingerprint = None
    if command.expected_fingerprint is not None:
        fingerprint = asdict(command.expected_fingerprint)
        fingerprint["included_paths"] = list(command.expected_fingerprint.included_paths)
    return {
        "model_version": "1.0", "document_ref": encode_ref(command.document_ref),
        "expected_snapshot_id": str(command.expected_snapshot_id),
        "expected_fingerprint": fingerprint,
        "targets": [encode_ref(ref) for ref in command.targets],
        "idempotency_key": command.idempotency_key,
        "guard_mode": command.guard_mode.value,
        "allow_scope_expansion": command.allow_scope_expansion,
        "ttl_ms": None if command.ttl is None else command.ttl.total_seconds() * 1000,
        "style": command.style.value, "replace_existing": command.replace_existing,
    }
