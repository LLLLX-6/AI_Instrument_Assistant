from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from ai_instrument_assistant.application.services.engineering_evidence import (
    DeterministicEngineeringComparator,
    EngineeringEvidenceAssembler,
    establish_evidence_cross_reference,
    locate_measurement_evidence,
    project_teaching_diagnosis,
)
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
    ComparisonReason,
    ComparisonStatus,
    CrossReferenceState,
    DesignEvidenceContext,
    DesignEvidenceItem,
    DesignEvidenceKind,
    DesignEvidenceOrigin,
    DiscreteExpectation,
    EngineeringMetric,
    EngineeringTarget,
    ExactNumericExpectation,
    NumericRangeExpectation,
    Quantity,
    RelativeTolerance,
    TargetProvenance,
    TrustedPhysicalConfirmationEvidence,
    VerificationState,
)
from ai_instrument_assistant.integrations.deepseek_harness.evidence_contract import EvidenceContractBinding


ROOT = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc)
SNAPSHOT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
MEASUREMENT_CONTEXT_ID = UUID("abababab-abab-4bab-8bab-abababababab")


def make_document() -> DesignDocument:
    return DesignDocument(
        document_ref=DesignObjectRef(
            provider="fixture-eda",
            object_type=DesignObjectKind.DOCUMENT,
            document_id="main_schematic",
            snapshot_id=SNAPSHOT_ID,
            native_id=None,
            canonical_id="project/document/main_schematic",
            display_name="main_schematic",
        ),
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


def make_probe() -> ProbeTarget:
    return ProbeTarget(
        target_id=UUID("12121212-1212-4121-8121-121212121212"),
        design_object=DesignObjectRef(
            provider="fixture-eda",
            object_type=DesignObjectKind.NET,
            document_id="main_schematic",
            snapshot_id=SNAPSHOT_ID,
            native_id=None,
            canonical_id="net/PWM_OUT",
            display_name="PWM_OUT",
        ),
        kind=ProbeTargetKind.DESIGN_ONLY,
    )


def make_design_evidence() -> tuple[DesignEvidenceItem, ...]:
    document = make_document()
    return (
        DesignEvidenceItem(
            evidence_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            kind=DesignEvidenceKind.TARGET_DECLARATION,
            label="PWM_OUT expected frequency",
            value=Quantity(10.0, "kHz"),
            unit="kHz",
            document=document,
            design_object=make_probe().design_object,
            verification_state=VerificationState.SNAPSHOT_BOUNDED,
            observed_at=NOW,
            origin=DesignEvidenceOrigin.DESIGN_DERIVED,
        ),
        DesignEvidenceItem(
            evidence_id=UUID("bcbcbcbc-bcbc-4bcb-8bcb-bcbcbcbcbcbc"),
            kind=DesignEvidenceKind.TARGET_DECLARATION,
            label="PWM_OUT expected duty",
            value=Quantity(30.0, "percent"),
            unit="percent",
            document=document,
            design_object=make_probe().design_object,
            verification_state=VerificationState.SNAPSHOT_BOUNDED,
            observed_at=NOW,
            origin=DesignEvidenceOrigin.DESIGN_DERIVED,
        ),
    )


def make_targets(*, tolerance: object | None = None) -> tuple[EngineeringTarget, ...]:
    evidence = make_design_evidence()
    return (
        EngineeringTarget(
            target_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
            metric=EngineeringMetric.FREQUENCY,
            expectation=ExactNumericExpectation(Quantity(10.0, "kHz")),
            tolerance=tolerance,
            provenance=TargetProvenance.DESIGN_DERIVED,
            source_evidence_ids=(evidence[0].evidence_id,),
        ),
        EngineeringTarget(
            target_id=UUID("cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd"),
            metric=EngineeringMetric.DUTY_CYCLE,
            expectation=ExactNumericExpectation(Quantity(30.0, "percent")),
            tolerance=None,
            provenance=TargetProvenance.DESIGN_DERIVED,
            source_evidence_ids=(evidence[1].evidence_id,),
        ),
    )


def teaching_context(filename: str = "pwm-teaching-context.case.json"):
    fixture = json.loads(
        (
            ROOT
            / "protocols"
            / "evidence"
            / "v1"
            / "fixtures"
            / "valid"
            / filename
        ).read_text(encoding="utf-8")
    )["instance"]
    return EvidenceContractBinding.from_repository(ROOT).parse_teaching_context(fixture)


def confirmation(*, channel: int = 1, target_ref: str = "net/PWM_OUT"):
    return TrustedPhysicalConfirmationEvidence(
        confirmation_id="confirmation-1",
        source="TRUSTED_USER_EVENT",
        confirmed_by="user",
        workflow_id="phase8-fixture",
        request_correlation_id="request-1",
        channel=channel,
        target_ref=target_ref,
        design_snapshot_id=SNAPSHOT_ID,
        probe_target_id=make_probe().target_id,
        safe_low_voltage_confirmed=True,
        common_ground_confirmed=True,
        wiring_unchanged=True,
        confirmed_at=NOW,
    )


def verified_link():
    return establish_evidence_cross_reference(
        cross_reference_id=UUID("99999999-9999-4999-8999-999999999999"),
        workflow_id="phase8-fixture",
        request_correlation_id="request-1",
        probe_target=make_probe(),
        confirmation=confirmation(),
        measurement_context_id=MEASUREMENT_CONTEXT_ID,
        measurement_channel=1,
        measured_at=NOW + timedelta(seconds=2),
    )


class CrossReferenceAndAssemblerTests(unittest.TestCase):
    def test_selection_or_probe_target_alone_cannot_create_verified_link(self) -> None:
        result = establish_evidence_cross_reference(
            cross_reference_id=UUID("99999999-9999-4999-8999-999999999999"),
            workflow_id="phase8-fixture",
            request_correlation_id="request-1",
            probe_target=make_probe(),
            confirmation=None,
            measurement_context_id=MEASUREMENT_CONTEXT_ID,
            measurement_channel=1,
            measured_at=NOW + timedelta(seconds=2),
        )
        self.assertEqual(result.state, CrossReferenceState.INSUFFICIENT_EVIDENCE)

    def test_label_match_does_not_override_channel_or_snapshot_mismatch(self) -> None:
        channel_mismatch = establish_evidence_cross_reference(
            cross_reference_id=UUID("99999999-9999-4999-8999-999999999999"),
            workflow_id="phase8-fixture",
            request_correlation_id="request-1",
            probe_target=make_probe(),
            confirmation=confirmation(channel=2),
            measurement_context_id=MEASUREMENT_CONTEXT_ID,
            measurement_channel=1,
            measured_at=NOW + timedelta(seconds=2),
        )
        self.assertEqual(channel_mismatch.state, CrossReferenceState.MISMATCH)
        self.assertIn("CHANNEL_MISMATCH", channel_mismatch.reasons)

        request_mismatch = establish_evidence_cross_reference(
            cross_reference_id=UUID("98989898-9898-4989-8989-989898989898"),
            workflow_id="phase8-fixture",
            request_correlation_id="different-request",
            probe_target=make_probe(),
            confirmation=confirmation(),
            measurement_context_id=MEASUREMENT_CONTEXT_ID,
            measurement_channel=1,
            measured_at=NOW + timedelta(seconds=2),
        )
        self.assertEqual(request_mismatch.state, CrossReferenceState.MISMATCH)
        self.assertIn("REQUEST_SCOPE_MISMATCH", request_mismatch.reasons)

    def test_verified_link_requires_trusted_temporal_and_scope_evidence(self) -> None:
        result = verified_link()
        self.assertEqual(result.state, CrossReferenceState.VERIFIED_LINK)
        self.assertLessEqual(result.confirmed_at, result.measured_at)
        self.assertEqual(result.measurement_channel, 1)

    def test_assembler_preserves_categories_and_generates_zero_inferences(self) -> None:
        evidence = make_design_evidence()
        context = EngineeringEvidenceAssembler().assemble(
            context_id=UUID("88888888-8888-4888-8888-888888888888"),
            workflow_id="phase8-fixture",
            user_goal="Compare PWM_OUT with design intent",
            assembled_at=NOW + timedelta(seconds=3),
            design_context=DesignEvidenceContext(
                document=make_document(),
                evidence=evidence,
                probe_targets=(make_probe(),),
                selection=None,
            ),
            targets=make_targets(),
            measurement_context_id=MEASUREMENT_CONTEXT_ID,
            measurement_context=teaching_context(),
            cross_references=(verified_link(),),
            comparison_results=(),
        )
        self.assertEqual(context.inferences, ())
        self.assertEqual(len(context.design_context.evidence), 2)
        self.assertEqual(len(context.measurement_context.facts), 1)
        self.assertEqual(len(context.measurement_context.analyses), 2)

        diagnosis = project_teaching_diagnosis(context)
        self.assertEqual(len(diagnosis.design_targets), 2)
        self.assertEqual(len(diagnosis.physical_observations), 1)
        self.assertEqual(len(diagnosis.software_analyses), 2)
        self.assertEqual(diagnosis.inferences, ())
        self.assertFalse(hasattr(diagnosis, "trusted_operation_scope"))

    def test_missing_measurement_stays_missing_and_becomes_unresolved(self) -> None:
        context = EngineeringEvidenceAssembler().assemble(
            context_id=UUID("88888888-8888-4888-8888-888888888888"),
            workflow_id="phase8-fixture",
            user_goal="Compare PWM_OUT",
            assembled_at=NOW,
            design_context=DesignEvidenceContext(
                document=make_document(), evidence=make_design_evidence(), probe_targets=(make_probe(),)
            ),
            targets=make_targets(),
            measurement_context_id=None,
            measurement_context=None,
            cross_references=(),
            comparison_results=(),
        )
        self.assertIsNone(context.measurement_context)
        self.assertIn("MEASUREMENT_MISSING", {item.code for item in context.unresolved_questions})


class ComparatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.comparator = DeterministicEngineeringComparator()
        self.context = teaching_context()
        self.located = locate_measurement_evidence(MEASUREMENT_CONTEXT_ID, self.context)
        self.instrument_frequency = next(
            item for item in self.located if item.locator.label == "instrument frequency"
        )
        self.software_frequency = next(
            item for item in self.located if item.locator.label == "software frequency"
        )

    def compare(self, target: EngineeringTarget, located=None, link=None):
        evidence = self.instrument_frequency if located is None else located
        return self.comparator.compare(
            target=target,
            observed=evidence.item,
            observed_ref=evidence.locator,
            cross_reference=verified_link() if link is None else link,
        )

    def test_exact_numeric_without_tolerance_is_indeterminate_but_has_difference(self) -> None:
        result = self.compare(make_targets()[0])
        self.assertEqual(result.status, ComparisonStatus.INDETERMINATE)
        self.assertEqual(result.reason, ComparisonReason.TOLERANCE_UNSPECIFIED)
        self.assertAlmostEqual(result.difference.value, 0.02)
        self.assertEqual(result.difference.unit, "kHz")

    def test_explicit_absolute_tolerance_matches_and_mismatches(self) -> None:
        match = make_targets(tolerance=AbsoluteTolerance(Quantity(0.03, "kHz")))[0]
        mismatch = make_targets(tolerance=AbsoluteTolerance(Quantity(0.01, "kHz")))[0]
        self.assertEqual(self.compare(match).status, ComparisonStatus.MATCH)
        self.assertEqual(self.compare(mismatch).status, ComparisonStatus.MISMATCH)

    def test_explicit_relative_tolerance_matches_and_mismatches(self) -> None:
        match = make_targets(tolerance=RelativeTolerance.from_percent(1.0))[0]
        mismatch = make_targets(tolerance=RelativeTolerance.from_percent(0.1))[0]
        far_item = self.software_frequency
        # 10.01 kHz is within both; use a bounded replacement for the mismatch case.
        near = self.compare(match, located=far_item)
        self.assertEqual(near.status, ComparisonStatus.MATCH)
        strict_target = EngineeringTarget(
            target_id=mismatch.target_id,
            metric=mismatch.metric,
            expectation=ExactNumericExpectation(Quantity(10.0, "kHz")),
            tolerance=RelativeTolerance.from_percent(0.01),
            provenance=mismatch.provenance,
            source_evidence_ids=mismatch.source_evidence_ids,
        )
        self.assertEqual(self.compare(strict_target, located=far_item).status, ComparisonStatus.MISMATCH)

    def test_explicit_range_matches_and_mismatches(self) -> None:
        source = make_design_evidence()[0]
        match = EngineeringTarget(
            target_id=UUID("45454545-4545-4454-8454-454545454545"),
            metric=EngineeringMetric.FREQUENCY,
            expectation=NumericRangeExpectation(9.9, 10.1, "kHz"),
            tolerance=None,
            provenance=TargetProvenance.DESIGN_DERIVED,
            source_evidence_ids=(source.evidence_id,),
        )
        mismatch = EngineeringTarget(
            target_id=UUID("46464646-4646-4464-8464-464646464646"),
            metric=EngineeringMetric.FREQUENCY,
            expectation=NumericRangeExpectation(9.0, 9.5, "kHz"),
            tolerance=None,
            provenance=TargetProvenance.DESIGN_DERIVED,
            source_evidence_ids=(source.evidence_id,),
        )
        self.assertEqual(self.compare(match).status, ComparisonStatus.MATCH)
        self.assertEqual(self.compare(mismatch).status, ComparisonStatus.MISMATCH)

    def test_supported_conversions_include_frequency_and_duty_cycle(self) -> None:
        frequency = self.compare(make_targets()[0])
        self.assertAlmostEqual(frequency.observed.value, 10.02)
        duty = next(item for item in self.located if item.locator.label == "software duty cycle")
        duty_result = self.comparator.compare(
            target=make_targets()[1],
            observed=duty.item,
            observed_ref=duty.locator,
            cross_reference=verified_link(),
        )
        self.assertAlmostEqual(duty_result.observed.value, 29.95)
        self.assertEqual(duty_result.reason, ComparisonReason.TOLERANCE_UNSPECIFIED)

    def test_incompatible_units_missing_unavailable_and_unverified_are_bounded(self) -> None:
        source = make_design_evidence()[0]
        incompatible_target = EngineeringTarget(
            target_id=UUID("47474747-4747-4474-8474-474747474747"),
            metric=EngineeringMetric.FREQUENCY,
            expectation=ExactNumericExpectation(Quantity(10.0, "V")),
            tolerance=AbsoluteTolerance(Quantity(1.0, "V")),
            provenance=TargetProvenance.DESIGN_DERIVED,
            source_evidence_ids=(source.evidence_id,),
        )
        self.assertEqual(
            self.compare(incompatible_target).reason,
            ComparisonReason.INCOMPATIBLE_UNIT,
        )
        missing = self.comparator.compare(
            target=make_targets()[0], observed=None, observed_ref=None, cross_reference=verified_link()
        )
        self.assertEqual(missing.reason, ComparisonReason.MEASUREMENT_MISSING)

        unavailable_context = teaching_context("unavailable-teaching-context.case.json")
        unavailable = locate_measurement_evidence(MEASUREMENT_CONTEXT_ID, unavailable_context)[0]
        self.assertEqual(
            self.comparator.compare(
                target=make_targets()[0],
                observed=unavailable.item,
                observed_ref=unavailable.locator,
                cross_reference=verified_link(),
            ).reason,
            ComparisonReason.OBSERVATION_UNAVAILABLE,
        )
        unverified = establish_evidence_cross_reference(
            cross_reference_id=UUID("48484848-4848-4484-8484-484848484848"),
            workflow_id="phase8-fixture", probe_target=make_probe(), confirmation=None,
            request_correlation_id="request-1",
            measurement_context_id=MEASUREMENT_CONTEXT_ID, measurement_channel=1,
            measured_at=NOW + timedelta(seconds=2),
        )
        result = self.compare(make_targets(tolerance=RelativeTolerance.from_percent(1))[0], link=unverified)
        self.assertEqual(result.status, ComparisonStatus.INDETERMINATE)
        self.assertEqual(result.reason, ComparisonReason.CROSS_REFERENCE_UNVERIFIED)

    def test_conflicting_sources_are_compared_separately_and_no_diagnosis_is_emitted(self) -> None:
        target = make_targets()[0]
        instrument = self.compare(target)
        software = self.compare(target, located=self.software_frequency)
        self.assertNotEqual(instrument.observed.value, software.observed.value)
        self.assertFalse(hasattr(instrument, "diagnosis"))

    def test_discrete_state_comparison_is_exact(self) -> None:
        source = make_design_evidence()[0]
        target = EngineeringTarget(
            target_id=UUID("49494949-4949-4494-8494-494949494949"),
            metric=EngineeringMetric.STATE,
            expectation=DiscreteExpectation("HIGH"),
            tolerance=None,
            provenance=TargetProvenance.USER_PROVIDED,
            source_evidence_ids=(source.evidence_id,),
        )
        # Numeric frequency is deliberately incompatible with a discrete state target.
        result = self.compare(target)
        self.assertEqual(result.status, ComparisonStatus.INDETERMINATE)
        self.assertEqual(result.reason, ComparisonReason.INCOMPATIBLE_METRIC)


if __name__ == "__main__":
    unittest.main()
