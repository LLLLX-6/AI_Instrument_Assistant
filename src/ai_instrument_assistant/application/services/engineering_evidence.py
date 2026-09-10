from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ...domain.eda.models import ProbeTarget
from ...domain.engineering_evidence import (
    AbsoluteTolerance,
    ComparisonReason,
    ComparisonResult,
    ComparisonStatus,
    CrossReferenceState,
    DesignEvidenceContext,
    DiscreteExpectation,
    EngineeringEvidenceContext,
    EngineeringMetric,
    EngineeringTarget,
    EvidenceCategory,
    EvidenceCollection,
    EvidenceCrossReference,
    EvidenceQuality,
    ExactNumericExpectation,
    LocatedEvidence,
    MeasurementEvidenceLocator,
    NumericRangeExpectation,
    Quantity,
    RelativeTolerance,
    TeachingDiagnosisContext,
    TeachingEvidenceContext,
    TeachingEvidenceItem,
    TrustedPhysicalConfirmationEvidence,
    UnresolvedQuestion,
)
from ...domain.errors import DomainInvariantError
from ...domain.values import DutyCycle


_METRIC_BY_LABEL = {
    "instrument frequency": EngineeringMetric.FREQUENCY,
    "software frequency": EngineeringMetric.FREQUENCY,
    "software duty cycle": EngineeringMetric.DUTY_CYCLE,
    "instrument vpp": EngineeringMetric.VOLTAGE,
    "software vpp": EngineeringMetric.VOLTAGE,
    "software mean": EngineeringMetric.VOLTAGE,
    "software rms": EngineeringMetric.VOLTAGE,
    "software period": EngineeringMetric.PERIOD,
}


def locate_measurement_evidence(
    measurement_context_id: UUID,
    context: TeachingEvidenceContext,
) -> tuple[LocatedEvidence, ...]:
    """Create stable bounded locators without adding IDs to the frozen context."""

    located: list[LocatedEvidence] = []
    for collection, items in (
        (EvidenceCollection.FACTS, context.facts),
        (EvidenceCollection.ANALYSES, context.analyses),
        (EvidenceCollection.INFERENCES, context.inferences),
    ):
        for ordinal, item in enumerate(items):
            located.append(
                LocatedEvidence(
                    locator=MeasurementEvidenceLocator(
                        measurement_context_id=measurement_context_id,
                        collection=collection,
                        ordinal=ordinal,
                        label=item.label,
                        metric=_METRIC_BY_LABEL.get(item.label, EngineeringMetric.OTHER),
                        category=item.category,
                    ),
                    item=item,
                )
            )
    return tuple(located)


def establish_evidence_cross_reference(
    *,
    cross_reference_id: UUID,
    workflow_id: str,
    request_correlation_id: str,
    probe_target: ProbeTarget | None,
    confirmation: TrustedPhysicalConfirmationEvidence | None,
    measurement_context_id: UUID,
    measurement_channel: int,
    measured_at: datetime,
) -> EvidenceCrossReference:
    """Evaluate supplied trusted linkage facts; labels alone never establish a link."""

    if probe_target is None or confirmation is None:
        reasons = []
        if probe_target is None:
            reasons.append("PROBE_TARGET_MISSING")
        if confirmation is None:
            reasons.append("TRUSTED_PHYSICAL_CONFIRMATION_MISSING")
        return EvidenceCrossReference(
            cross_reference_id=cross_reference_id,
            state=CrossReferenceState.INSUFFICIENT_EVIDENCE,
            reasons=tuple(reasons),
            workflow_id=workflow_id,
            probe_target_id=None if probe_target is None else probe_target.target_id,
            design_snapshot_id=None if probe_target is None else probe_target.snapshot_id,
            confirmation_id=None if confirmation is None else confirmation.confirmation_id,
            confirmation_source=None if confirmation is None else confirmation.source,
            confirmed_by=None if confirmation is None else confirmation.confirmed_by,
            confirmed_target_ref=None if confirmation is None else confirmation.target_ref,
            request_correlation_id=None if confirmation is None else confirmation.request_correlation_id,
            measurement_context_id=measurement_context_id,
            measurement_channel=measurement_channel,
            confirmed_at=None,
            measured_at=measured_at,
        )

    reasons: list[str] = []
    if confirmation.workflow_id != workflow_id:
        reasons.append("WORKFLOW_MISMATCH")
    if confirmation.request_correlation_id != request_correlation_id:
        reasons.append("REQUEST_SCOPE_MISMATCH")
    if confirmation.channel != measurement_channel:
        reasons.append("CHANNEL_MISMATCH")
    if confirmation.design_snapshot_id != probe_target.snapshot_id:
        reasons.append("SNAPSHOT_MISMATCH")
    if confirmation.probe_target_id != probe_target.target_id:
        reasons.append("PROBE_TARGET_MISMATCH")
    if confirmation.target_ref != probe_target.design_object.canonical_id:
        reasons.append("TARGET_REFERENCE_MISMATCH")
    if confirmation.confirmed_at > measured_at:
        reasons.append("TEMPORAL_ORDER_MISMATCH")

    return EvidenceCrossReference(
        cross_reference_id=cross_reference_id,
        state=CrossReferenceState.MISMATCH if reasons else CrossReferenceState.VERIFIED_LINK,
        reasons=tuple(reasons),
        workflow_id=workflow_id,
        probe_target_id=probe_target.target_id,
        design_snapshot_id=probe_target.snapshot_id,
        confirmation_id=confirmation.confirmation_id,
        confirmation_source=confirmation.source,
        confirmed_by=confirmation.confirmed_by,
        confirmed_target_ref=confirmation.target_ref,
        request_correlation_id=confirmation.request_correlation_id,
        measurement_context_id=measurement_context_id,
        measurement_channel=measurement_channel,
        confirmed_at=confirmation.confirmed_at,
        measured_at=measured_at,
    )


class EngineeringEvidenceAssembler:
    """Composes existing evidence without invention, diagnosis, or inference."""

    def validate_design_and_targets(
        self,
        *,
        design_context: DesignEvidenceContext | None,
        targets: tuple[EngineeringTarget, ...],
    ) -> None:
        """Validate source identity/provenance before linkage or comparison."""

        target_values = tuple(targets)
        if len({target.target_id for target in target_values}) != len(target_values):
            raise DomainInvariantError("engineering target identifiers must be unique")
        if design_context is None:
            if target_values:
                raise DomainInvariantError("targets require a design evidence context")
            return

        design_by_id = {item.evidence_id: item for item in design_context.evidence}
        for target in target_values:
            for source_id in target.source_evidence_ids:
                source = design_by_id.get(source_id)
                if source is None:
                    raise DomainInvariantError("target references missing design evidence")
                if source.category is not EvidenceCategory.DESIGN_TARGET:
                    raise DomainInvariantError("target source must remain DESIGN_TARGET evidence")
                expected_origin = (
                    "DESIGN_DERIVED"
                    if target.provenance.value == "DESIGN_DERIVED"
                    else "USER_STATEMENT"
                )
                if source.origin.value != expected_origin:
                    raise DomainInvariantError("target provenance must match source evidence origin")

    def assemble(
        self,
        *,
        context_id: UUID,
        workflow_id: str,
        user_goal: str,
        assembled_at: datetime,
        design_context: DesignEvidenceContext | None,
        targets: tuple[EngineeringTarget, ...],
        measurement_context_id: UUID | None,
        measurement_context: TeachingEvidenceContext | None,
        cross_references: tuple[EvidenceCrossReference, ...],
        comparison_results: tuple[ComparisonResult, ...],
    ) -> EngineeringEvidenceContext:
        target_values = tuple(targets)
        cross_values = tuple(cross_references)
        comparison_values = tuple(comparison_results)
        unresolved: list[UnresolvedQuestion] = []
        self.validate_design_and_targets(
            design_context=design_context,
            targets=target_values,
        )

        if design_context is None:
            unresolved.append(UnresolvedQuestion("DESIGN_EVIDENCE_MISSING", None, "No design evidence context was supplied."))
        else:
            if (
                design_context.selection is not None
                and len(design_context.selection.selection.selected_objects) > 1
                and design_context.selection.selection.primary_object is None
            ):
                unresolved.append(
                    UnresolvedQuestion(
                        "AMBIGUOUS_DESIGN_SELECTION",
                        None,
                        "Multiple design objects are selected without an explicit primary object.",
                    )
                )

        if not target_values:
            unresolved.append(UnresolvedQuestion("TARGET_MISSING", None, "No explicit engineering target was supplied."))
        if measurement_context is None:
            unresolved.append(UnresolvedQuestion("MEASUREMENT_MISSING", None, "No measurement evidence context was supplied."))
        if measurement_context is not None and not any(
            item.state is CrossReferenceState.VERIFIED_LINK for item in cross_values
        ):
            unresolved.append(UnresolvedQuestion("PHYSICAL_LINK_UNVERIFIED", None, "No trusted cross-reference links the design target to the measurement."))

        for link in cross_values:
            if link.workflow_id != workflow_id:
                raise DomainInvariantError("cross-reference workflow must match assembled workflow")
            if link.measurement_context_id != measurement_context_id:
                raise DomainInvariantError("cross-reference measurement context must match")
            if (
                design_context is not None
                and link.design_snapshot_id is not None
                and link.design_snapshot_id != design_context.document.snapshot_id
            ):
                raise DomainInvariantError("cross-reference design snapshot must match")

        target_ids = {target.target_id for target in target_values}
        for comparison in comparison_values:
            if comparison.target_id not in target_ids:
                raise DomainInvariantError("comparison references an unknown target")
            if comparison.observed_ref is not None and comparison.observed_ref.measurement_context_id != measurement_context_id:
                raise DomainInvariantError("comparison evidence belongs to another measurement context")

        limitations = measurement_context.limitations if measurement_context else ()
        return EngineeringEvidenceContext(
            context_id=context_id,
            workflow_id=workflow_id,
            user_goal=user_goal,
            assembled_at=assembled_at,
            design_context=design_context,
            targets=target_values,
            measurement_context_id=measurement_context_id,
            measurement_context=measurement_context,
            cross_references=cross_values,
            comparison_results=comparison_values,
            limitations=limitations,
            unresolved_questions=tuple(unresolved),
            inferences=(),
        )


class DeterministicEngineeringComparator:
    """Explicit-tolerance comparator with a closed deterministic unit allowlist."""

    def compare(
        self,
        *,
        target: EngineeringTarget,
        observed: TeachingEvidenceItem | None,
        observed_ref: MeasurementEvidenceLocator | None,
        cross_reference: EvidenceCrossReference | None,
    ) -> ComparisonResult:
        if observed is None or observed_ref is None:
            return self._indeterminate(target, observed_ref, ComparisonReason.MEASUREMENT_MISSING)
        if observed_ref.metric is not target.metric:
            return self._indeterminate(target, observed_ref, ComparisonReason.INCOMPATIBLE_METRIC)
        if observed.quality is EvidenceQuality.UNAVAILABLE or observed.value is None:
            return self._indeterminate(target, observed_ref, ComparisonReason.OBSERVATION_UNAVAILABLE)
        if cross_reference is None or cross_reference.state is not CrossReferenceState.VERIFIED_LINK:
            return self._indeterminate(target, observed_ref, ComparisonReason.CROSS_REFERENCE_UNVERIFIED)

        if isinstance(target.expectation, DiscreteExpectation):
            if not isinstance(observed.value, (str, bool)):
                return self._indeterminate(target, observed_ref, ComparisonReason.NON_NUMERIC_OBSERVATION)
            equal = observed.value == target.expectation.value
            return ComparisonResult(
                metric=target.metric, target_id=target.target_id, observed_ref=observed_ref,
                expected=target.expectation, observed=observed.value, difference=None,
                relative_difference=None,
                status=ComparisonStatus.MATCH if equal else ComparisonStatus.MISMATCH,
                reason=ComparisonReason.DISCRETE_EQUAL if equal else ComparisonReason.DISCRETE_DIFFERENT,
            )

        observed_quantity = _observed_quantity(observed)
        if observed_quantity is None:
            return self._indeterminate(target, observed_ref, ComparisonReason.NON_NUMERIC_OBSERVATION)
        target_unit = (
            target.expectation.quantity.unit
            if isinstance(target.expectation, ExactNumericExpectation)
            else target.expectation.unit
        )
        converted = _convert_quantity(observed_quantity, target_unit)
        if converted is None:
            return self._indeterminate(target, observed_ref, ComparisonReason.INCOMPATIBLE_UNIT)

        if isinstance(target.expectation, NumericRangeExpectation):
            if converted.value < target.expectation.minimum:
                difference = converted.value - target.expectation.minimum
            elif converted.value > target.expectation.maximum:
                difference = converted.value - target.expectation.maximum
            else:
                difference = 0.0
            match = target.expectation.minimum <= converted.value <= target.expectation.maximum
            return ComparisonResult(
                metric=target.metric, target_id=target.target_id, observed_ref=observed_ref,
                expected=target.expectation, observed=converted,
                difference=Quantity(difference, target_unit), relative_difference=None,
                status=ComparisonStatus.MATCH if match else ComparisonStatus.MISMATCH,
                reason=ComparisonReason.WITHIN_RANGE if match else ComparisonReason.OUTSIDE_RANGE,
            )

        expected = target.expectation.quantity
        difference_value = converted.value - expected.value
        difference = Quantity(difference_value, expected.unit)
        relative = None if expected.value == 0 else abs(difference_value) / abs(expected.value)
        if target.tolerance is None:
            return ComparisonResult(
                metric=target.metric, target_id=target.target_id, observed_ref=observed_ref,
                expected=target.expectation, observed=converted, difference=difference,
                relative_difference=relative, status=ComparisonStatus.INDETERMINATE,
                reason=ComparisonReason.TOLERANCE_UNSPECIFIED,
            )
        if isinstance(target.tolerance, AbsoluteTolerance):
            tolerance = _convert_quantity(target.tolerance.quantity, expected.unit)
            if tolerance is None:
                return self._indeterminate(target, observed_ref, ComparisonReason.INCOMPATIBLE_UNIT)
            match = abs(difference_value) <= tolerance.value
        elif isinstance(target.tolerance, RelativeTolerance):
            if relative is None:
                return ComparisonResult(
                    metric=target.metric, target_id=target.target_id, observed_ref=observed_ref,
                    expected=target.expectation, observed=converted, difference=difference,
                    relative_difference=None, status=ComparisonStatus.INDETERMINATE,
                    reason=ComparisonReason.RELATIVE_DIFFERENCE_UNDEFINED,
                )
            match = relative <= target.tolerance.ratio
        else:  # pragma: no cover - protected by domain invariant
            raise DomainInvariantError("unsupported tolerance")
        return ComparisonResult(
            metric=target.metric, target_id=target.target_id, observed_ref=observed_ref,
            expected=target.expectation, observed=converted, difference=difference,
            relative_difference=relative,
            status=ComparisonStatus.MATCH if match else ComparisonStatus.MISMATCH,
            reason=ComparisonReason.WITHIN_TOLERANCE if match else ComparisonReason.OUTSIDE_TOLERANCE,
        )

    @staticmethod
    def _indeterminate(target, observed_ref, reason) -> ComparisonResult:
        return ComparisonResult(
            metric=target.metric, target_id=target.target_id, observed_ref=observed_ref,
            expected=target.expectation, observed=None, difference=None,
            relative_difference=None, status=ComparisonStatus.INDETERMINATE, reason=reason,
        )


def project_teaching_diagnosis(context: EngineeringEvidenceContext) -> TeachingDiagnosisContext:
    located = () if context.measurement_context is None else locate_measurement_evidence(
        context.measurement_context_id, context.measurement_context
    )
    design_facts = () if context.design_context is None else tuple(
        item for item in context.design_context.evidence if item.category is EvidenceCategory.DESIGN_FACT
    )
    return TeachingDiagnosisContext(
        goal=context.user_goal,
        design_facts=design_facts,
        design_targets=context.targets,
        physical_observations=tuple(item for item in located if item.locator.category is EvidenceCategory.PHYSICAL_FACT),
        software_analyses=tuple(item for item in located if item.locator.category is EvidenceCategory.SOFTWARE_ANALYSIS),
        simulated_evidence=tuple(item for item in located if item.locator.category is EvidenceCategory.SIMULATED_EVIDENCE),
        comparisons=context.comparison_results,
        quality=None if context.measurement_context is None else context.measurement_context.quality,
        warnings=() if context.measurement_context is None else context.measurement_context.warnings,
        coherence=None if context.measurement_context is None else context.measurement_context.coherence,
        limitations=context.limitations,
        unresolved_questions=context.unresolved_questions,
        candidate_next_measurements=(),
        inferences=(),
    )


def _observed_quantity(item: TeachingEvidenceItem) -> Quantity | None:
    if isinstance(item.value, DutyCycle):
        return Quantity(item.value.ratio, "ratio")
    if isinstance(item.value, (int, float)) and not isinstance(item.value, bool) and item.unit:
        return Quantity(float(item.value), item.unit)
    return None


_UNITS = {
    "Hz": ("frequency", 1.0),
    "kHz": ("frequency", 1000.0),
    "V": ("voltage", 1.0),
    "mV": ("voltage", 0.001),
    "s": ("time", 1.0),
    "ms": ("time", 0.001),
    "us": ("time", 0.000001),
    "µs": ("time", 0.000001),
    "ratio": ("duty", 1.0),
    "percent": ("duty", 0.01),
    "%": ("duty", 0.01),
}


def _convert_quantity(value: Quantity, target_unit: str) -> Quantity | None:
    source = _UNITS.get(value.unit)
    target = _UNITS.get(target_unit)
    if source is None or target is None or source[0] != target[0]:
        return None
    base = value.value * source[1]
    return Quantity(base / target[1], target_unit)
