from __future__ import annotations

from .models import (
    AllowedClaimEnvelope,
    ClaimDecision,
    ClaimKind,
    DeterministicFallback,
)


_FALLBACK_KINDS = frozenset(
    {
        ClaimKind.EVIDENCE_RESTATEMENT,
        ClaimKind.DETERMINISTIC_COMPARISON_STATEMENT,
        ClaimKind.LIMITATION_STATEMENT,
    }
)


def build_deterministic_fallback(envelope: AllowedClaimEnvelope) -> DeterministicFallback:
    """Project allowed evidence-only slots without generating text or retrying."""

    if not isinstance(envelope, AllowedClaimEnvelope):
        raise TypeError("envelope must be AllowedClaimEnvelope")
    permissions = tuple(
        item
        for item in envelope.permissions
        if item.decision is ClaimDecision.ALLOW and item.claim_kind in _FALLBACK_KINDS
    )
    return DeterministicFallback(
        envelope_id=envelope.envelope_id,
        context_fingerprint=envelope.context_fingerprint,
        permissions=permissions,
    )
