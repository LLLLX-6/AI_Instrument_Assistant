from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ai_instrument_assistant.application.experiments import (
    RCFrequencyPointMeasurement,
    RCLowPassMeasurementPlan,
    RCSinglePointMeasurementAnalyzer,
)
from ai_instrument_assistant.application.tool_contracts.hardware_result_mapper import (
    CanonicalMeasurementResultMapper,
)
from ai_instrument_assistant.domain.measurement import MeasurementResult


_ORDER = (
    ("hardware.measure_frequency", 1),
    ("hardware.measure_vpp", 1),
    ("hardware.measure_frequency", 2),
    ("hardware.measure_vpp", 2),
)


class Re001CLiteValidationError(ValueError):
    """Bounded failure while consuming the private governed receipt."""


@dataclass(frozen=True, slots=True)
class GovernedMeasurementBundle:
    """Strictly mapped physical inputs plus the existing deterministic analysis."""

    measurements: tuple[MeasurementResult, MeasurementResult, MeasurementResult, MeasurementResult]
    analysis: RCFrequencyPointMeasurement


def analyze_governed_receipt(
    plan: RCLowPassMeasurementPlan,
    receipt: Mapping[str, Any],
    *,
    mapper: CanonicalMeasurementResultMapper | None = None,
    analyzer: RCSinglePointMeasurementAnalyzer | None = None,
) -> RCFrequencyPointMeasurement:
    """Map four explicit canonical results, then delegate all RC math to RE-001B."""
    return map_and_analyze_governed_receipt(
        plan,
        receipt,
        mapper=mapper,
        analyzer=analyzer,
    ).analysis


def map_and_analyze_governed_receipt(
    plan: RCLowPassMeasurementPlan,
    receipt: Mapping[str, Any],
    *,
    mapper: CanonicalMeasurementResultMapper | None = None,
    analyzer: RCSinglePointMeasurementAnalyzer | None = None,
) -> GovernedMeasurementBundle:
    """Return mapped evidence without letting callers copy canonical numbers."""
    if receipt.get("contract") != "aia-re001c-lite-validation" or receipt.get("status") != "COMPLETED":
        raise Re001CLiteValidationError("governed_measurement_not_completed")
    operations = receipt.get("operations")
    if not isinstance(operations, list) or len(operations) != len(_ORDER):
        raise Re001CLiteValidationError("governed_operation_receipt_invalid")
    result_mapper = mapper or CanonicalMeasurementResultMapper()
    mapped = []
    for item, (expected_operation, expected_channel) in zip(operations, _ORDER, strict=True):
        if not isinstance(item, Mapping):
            raise Re001CLiteValidationError("governed_operation_receipt_invalid")
        if item.get("operation") != expected_operation or item.get("channel") != expected_channel:
            raise Re001CLiteValidationError("governed_operation_binding_mismatch")
        if item.get("ipc_dispatch_count") != 1 or item.get("hardware_execution_count") != 1:
            raise Re001CLiteValidationError("governed_execution_count_invalid")
        if item.get("scope_remaining_invocations") != 0:
            raise Re001CLiteValidationError("governed_scope_budget_invalid")
        if item.get("policy_reason") != "allowed_confirmed_physical_setup":
            raise Re001CLiteValidationError("governed_physical_policy_invalid")
        canonical = item.get("canonical_result")
        if isinstance(canonical, Mapping) and canonical.get("ok") is False:
            result_mapper.map_failure(
                canonical,
                expected_operation=expected_operation,
                expected_channel=expected_channel,
            )
            raise Re001CLiteValidationError("canonical_measurement_failed")
        mapped.append(result_mapper.map_success(
            canonical,
            expected_operation=expected_operation,
            expected_channel=expected_channel,
        ))
    if len(mapped) != 4:  # pragma: no cover - guarded by receipt cardinality
        raise Re001CLiteValidationError("governed_operation_receipt_invalid")
    typed = (mapped[0], mapped[1], mapped[2], mapped[3])
    analysis = (analyzer or RCSinglePointMeasurementAnalyzer()).analyze(
        plan,
        vin_frequency=typed[0],
        vin_vpp=typed[1],
        vout_frequency=typed[2],
        vout_vpp=typed[3],
    )
    return GovernedMeasurementBundle(typed, analysis)
