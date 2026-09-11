from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
from uuid import UUID

from ..models import AllowedClaimEnvelope, ClaimPermission


def permission_content_id(
    envelope: AllowedClaimEnvelope,
    permission: ClaimPermission,
) -> str:
    """Return a complete permission content identity, not trust or authority."""

    canonical = {
        "envelope_id": envelope.envelope_id,
        "context_fingerprint": envelope.context_fingerprint,
        "goal": envelope.goal,
        "policy_name": envelope.policy_name,
        "policy_version": envelope.policy_version,
        "permission": permission,
    }
    return content_identity(canonical)


def content_identity(value: object) -> str:
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _canonical(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
