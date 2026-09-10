from __future__ import annotations

from typing import Protocol

from ...domain.engineering_evidence import (
    ComparisonResult,
    EngineeringTarget,
    EvidenceCrossReference,
    MeasurementEvidenceLocator,
    TeachingEvidenceItem,
)


class EngineeringComparator(Protocol):
    """Provider-neutral deterministic comparison port; it performs no diagnosis."""

    def compare(
        self,
        *,
        target: EngineeringTarget,
        observed: TeachingEvidenceItem | None,
        observed_ref: MeasurementEvidenceLocator | None,
        cross_reference: EvidenceCrossReference | None,
    ) -> ComparisonResult: ...
