from __future__ import annotations

import unittest

from ai_instrument_assistant.application.experiments import (
    RCDesignContextSource,
    RCEvidenceSource,
    RCLowPassMeasurementPlanner,
)
from ai_instrument_assistant.domain.measurement import ObservationSource
from tests.unit.application.tool_contracts.test_hardware_result_mapper import canonical
from validation.support.re001c_lite import Re001CLiteValidationError, analyze_governed_receipt


def completed_receipt() -> dict:
    values = (
        ("hardware.measure_frequency", "frequency", 1, 100.0),
        ("hardware.measure_vpp", "vpp", 1, 3.2),
        ("hardware.measure_frequency", "frequency", 2, 100.1),
        ("hardware.measure_vpp", "vpp", 2, 2.0),
    )
    return {
        "contract": "aia-re001c-lite-validation",
        "status": "COMPLETED",
        "operations": [
            {
                "operation": operation,
                "channel": channel,
                "scope_remaining_invocations": 0,
                "policy_reason": "allowed_confirmed_physical_setup",
                "ipc_dispatch_count": 1,
                "hardware_execution_count": 1,
                "canonical_result": canonical(operation, kind, channel, value),
                "failure_code": None,
            }
            for operation, kind, channel, value in values
        ],
        "failure_code": None,
    }


class Re001CLiteCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = RCLowPassMeasurementPlanner().from_user_declared_design(
            requested_frequency_hz=100.0,
            vin="STM32 output at CH1",
            vout="STM32 output at CH2",
            reference="common GND",
        )

    def test_fake_e2e_maps_only_canonical_results_before_existing_analyzer(self) -> None:
        result = analyze_governed_receipt(self.plan, completed_receipt())
        self.assertIs(self.plan.design_context_source, RCDesignContextSource.USER_DECLARED_DESIGN_CONTEXT)
        self.assertAlmostEqual(0.625, result.gain_ratio)
        self.assertAlmostEqual(-4.082399653, result.gain_db)
        self.assertIs(result.vin.source, RCEvidenceSource.PHYSICAL_MEASUREMENT)
        self.assertIs(result.vout.source, RCEvidenceSource.PHYSICAL_MEASUREMENT)
        self.assertIs(result.analysis_source, RCEvidenceSource.SOFTWARE_ANALYSIS)
        for operation in completed_receipt()["operations"]:
            observation = next(iter(operation["canonical_result"]["result"]["observations"].values()))
            self.assertEqual(ObservationSource.INSTRUMENT.value, observation["source"])

    def test_explicit_binding_not_array_order_controls_mapping(self) -> None:
        receipt = completed_receipt()
        receipt["operations"][1], receipt["operations"][2] = receipt["operations"][2], receipt["operations"][1]
        with self.assertRaisesRegex(Re001CLiteValidationError, "binding"):
            analyze_governed_receipt(self.plan, receipt)

    def test_failed_canonical_result_is_bounded_and_never_analyzed(self) -> None:
        receipt = completed_receipt()
        receipt["status"] = "FAILED"
        receipt["operations"] = receipt["operations"][:2]
        receipt["operations"][1]["canonical_result"] = {
            "contract_version": "1.0", "ok": False,
            "operation": "hardware.measure_vpp",
            "error": {"code": "measurement_failed", "message": "failed", "details": {}},
        }
        with self.assertRaisesRegex(Re001CLiteValidationError, "not_completed"):
            analyze_governed_receipt(self.plan, receipt)


if __name__ == "__main__":
    unittest.main()
