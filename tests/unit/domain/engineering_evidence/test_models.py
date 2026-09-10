from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import UUID

from ai_instrument_assistant.domain.eda.models import (
    DesignDocument,
    DesignFingerprint,
    DesignObjectKind,
    DesignObjectRef,
    ProbeTarget,
    ProbeTargetKind,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    AbsoluteTolerance,
    DesignEvidenceItem,
    DesignEvidenceKind,
    DesignEvidenceOrigin,
    DiscreteExpectation,
    EngineeringMetric,
    EngineeringTarget,
    EvidenceCategory,
    ExactNumericExpectation,
    NumericRangeExpectation,
    Quantity,
    RelativeTolerance,
    TargetProvenance,
    VerificationState,
    TeachingEvidenceItem,
    TeachingEvidenceKind,
    TeachingEvidenceProvenance,
    TeachingEvidenceSource,
    EvidenceQuality,
)
from ai_instrument_assistant.domain.errors import DomainInvariantError


NOW = datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc)
SNAPSHOT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def document(provider: str = "fixture-eda") -> DesignDocument:
    ref = DesignObjectRef(
        provider=provider,
        object_type=DesignObjectKind.DOCUMENT,
        document_id="main_schematic",
        snapshot_id=SNAPSHOT_ID,
        native_id=None,
        canonical_id="project/document/main_schematic",
        display_name="main_schematic",
    )
    return DesignDocument(
        document_ref=ref,
        project_id="STM32_Test",
        project_name="STM32_Test",
        document_name="main_schematic",
        document_type="schematic",
        native_revision=None,
        fingerprint=DesignFingerprint(
            value="sha256:bounded",
            scope_kind="document_projection",
            scope_version="1",
            included_paths=("document", "selection"),
        ),
        is_dirty=False,
        captured_at=NOW,
    )


def target_evidence() -> DesignEvidenceItem:
    return DesignEvidenceItem(
        evidence_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        kind=DesignEvidenceKind.TARGET_DECLARATION,
        label="PWM_OUT expected frequency",
        value=Quantity(10.0, "kHz"),
        unit="kHz",
        document=document(),
        design_object=None,
        verification_state=VerificationState.SNAPSHOT_BOUNDED,
        observed_at=NOW,
        origin=DesignEvidenceOrigin.DESIGN_DERIVED,
    )


class EngineeringEvidenceModelTests(unittest.TestCase):
    def test_design_target_is_structurally_distinct_from_physical_fact(self) -> None:
        item = target_evidence()
        self.assertEqual(item.category, EvidenceCategory.DESIGN_TARGET)
        self.assertNotEqual(item.category, EvidenceCategory.PHYSICAL_FACT)

    def test_provider_is_not_fixed_to_jlceda(self) -> None:
        self.assertEqual(document("kicad").document_ref.provider, "kicad")

    def test_models_are_immutable(self) -> None:
        item = target_evidence()
        with self.assertRaises(FrozenInstanceError):
            item.label = "changed"  # type: ignore[misc]

    def test_target_forms_and_tolerances_are_explicit(self) -> None:
        evidence = target_evidence()
        exact = EngineeringTarget(
            target_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
            metric=EngineeringMetric.FREQUENCY,
            expectation=ExactNumericExpectation(Quantity(10.0, "kHz")),
            tolerance=RelativeTolerance.from_percent(1.0),
            provenance=TargetProvenance.DESIGN_DERIVED,
            source_evidence_ids=(evidence.evidence_id,),
        )
        bounded = EngineeringTarget(
            target_id=UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
            metric=EngineeringMetric.VOLTAGE,
            expectation=NumericRangeExpectation(0.0, 3.3, "V"),
            tolerance=None,
            provenance=TargetProvenance.USER_PROVIDED,
            source_evidence_ids=(evidence.evidence_id,),
        )
        discrete = EngineeringTarget(
            target_id=UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
            metric=EngineeringMetric.STATE,
            expectation=DiscreteExpectation("HIGH"),
            tolerance=None,
            provenance=TargetProvenance.DESIGN_DERIVED,
            source_evidence_ids=(evidence.evidence_id,),
        )
        self.assertAlmostEqual(exact.tolerance.ratio, 0.01)
        self.assertEqual(bounded.expectation.maximum, 3.3)
        self.assertEqual(discrete.expectation.value, "HIGH")

        with self.assertRaises(DomainInvariantError):
            EngineeringTarget(
                target_id=UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
                metric=EngineeringMetric.VOLTAGE,
                expectation=NumericRangeExpectation(0.0, 3.3, "V"),
                tolerance=AbsoluteTolerance(Quantity(0.1, "V")),
                provenance=TargetProvenance.USER_PROVIDED,
                source_evidence_ids=(evidence.evidence_id,),
            )

    def test_probe_target_remains_only_a_candidate(self) -> None:
        net = DesignObjectRef(
            provider="fixture-eda",
            object_type=DesignObjectKind.NET,
            document_id="main_schematic",
            snapshot_id=SNAPSHOT_ID,
            native_id=None,
            canonical_id="net/PWM_OUT",
            display_name="PWM_OUT",
        )
        candidate = ProbeTarget(
            target_id=UUID("12121212-1212-4121-8121-121212121212"),
            design_object=net,
            kind=ProbeTargetKind.DESIGN_ONLY,
        )
        self.assertEqual(candidate.kind, ProbeTargetKind.DESIGN_ONLY)
        self.assertFalse(hasattr(candidate, "confirmed_at"))

    def test_measurement_categories_cannot_be_relabelled(self) -> None:
        provenance = TeachingEvidenceProvenance("fixture", NOW, None)
        physical = TeachingEvidenceItem(
            TeachingEvidenceKind.FACT, "frequency", 10000.0, "Hz",
            TeachingEvidenceSource.INSTRUMENT, EvidenceQuality.GOOD, (), provenance,
        )
        software = TeachingEvidenceItem(
            TeachingEvidenceKind.ANALYSIS, "frequency", 10010.0, "Hz",
            TeachingEvidenceSource.SOFTWARE_ANALYSIS, EvidenceQuality.GOOD, (), provenance,
        )
        simulated = TeachingEvidenceItem(
            TeachingEvidenceKind.FACT, "frequency", 9990.0, "Hz",
            TeachingEvidenceSource.SIMULATED, EvidenceQuality.GOOD, (), provenance,
        )
        self.assertEqual(physical.category, EvidenceCategory.PHYSICAL_FACT)
        self.assertNotEqual(physical.category, EvidenceCategory.DESIGN_FACT)
        self.assertEqual(software.category, EvidenceCategory.SOFTWARE_ANALYSIS)
        self.assertEqual(simulated.category, EvidenceCategory.SIMULATED_EVIDENCE)

        with self.assertRaises(DomainInvariantError):
            TeachingEvidenceItem(
                TeachingEvidenceKind.FACT, "bad", 1.0, "Hz",
                TeachingEvidenceSource.SOFTWARE_ANALYSIS, EvidenceQuality.GOOD, (), provenance,
            )


if __name__ == "__main__":
    unittest.main()
