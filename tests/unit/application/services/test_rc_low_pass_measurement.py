from __future__ import annotations

import math
import unittest
from dataclasses import fields
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from ai_instrument_assistant.application.experiments.rc_low_pass import (
    RCFilterExperimentSpec,
    RCLowPassExperimentService,
)
from ai_instrument_assistant.application.experiments.rc_low_pass_measurement import (
    RCDesignContextSource,
    RCEvidenceSource,
    RCFrequencyPointMeasurement,
    RCLowPassMeasurementPlan,
    RCLowPassMeasurementPlanner,
    RCMeasurementAnalysisError,
    RCNodeRoleKind,
    RCSinglePointMeasurementAnalyzer,
)
from ai_instrument_assistant.domain.artifacts import ArtifactReference, WaveformArtifact
from ai_instrument_assistant.domain.instrument import InstrumentIdentity
from ai_instrument_assistant.domain.measurement import (
    MeasurementCoherence,
    MeasurementKind,
    MeasurementObservation,
    MeasurementProvenance,
    MeasurementQuality,
    MeasurementRequest,
    MeasurementResult,
    ObservationQuality,
    ObservationSource,
)
from tests.unit.application.services.test_rc_low_pass_experiment import (
    RecordedEDA,
    rc_observation,
)


NOW = datetime(2026, 9, 13, 16, 0, tzinfo=UTC)
IDENTITY = InstrumentIdentity("RIGOL", "DS1102Z-E", "***", "test")


def result(kind: MeasurementKind, channel: int, value: float) -> MeasurementResult:
    identifier = uuid5(NAMESPACE_URL, f"re001b:{kind.value}:{channel}")
    observation = MeasurementObservation(
        value=value,
        source=ObservationSource.INSTRUMENT,
        method=f"oscilloscope.measure_{kind.value}",
        observed_at=NOW,
        quality=ObservationQuality.GOOD,
    )
    return MeasurementResult(
        request=MeasurementRequest(identifier, kind, channel, "re001b-test"),
        waveform=None,
        quality=MeasurementQuality.GOOD,
        warnings=(),
        coherence=MeasurementCoherence.unknown(),
        provenance=MeasurementProvenance(IDENTITY, channel, NOW, NOW),
        instrument_frequency=observation if kind is MeasurementKind.FREQUENCY else None,
        instrument_vpp=observation if kind is MeasurementKind.VPP else None,
    )


def waveform_result(channel: int) -> MeasurementResult:
    identifier = uuid5(NAMESPACE_URL, f"re001b:waveform:{channel}")
    reference = ArtifactReference(
        uuid5(NAMESPACE_URL, f"re001b:artifact:{channel}"),
        f"memory:re001b-channel-{channel}",
        "application/vnd.aia.waveform",
    )
    waveform = WaveformArtifact(
        reference, channel, 100, 1e-5, 0.0, 0.001, -1.0, 1.0, "normal", NOW,
    )
    return MeasurementResult(
        request=MeasurementRequest(identifier, MeasurementKind.WAVEFORM, channel, "re001b-test"),
        waveform=waveform,
        quality=MeasurementQuality.GOOD,
        warnings=(),
        coherence=MeasurementCoherence.unknown(),
        provenance=MeasurementProvenance(IDENTITY, channel, NOW, NOW),
    )


class RCMeasurementPlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_observed_design_creates_fixed_single_point_plan(self) -> None:
        design = await RCLowPassExperimentService(RecordedEDA(rc_observation())).evaluate(
            RCFilterExperimentSpec(1_000.0)
        )
        plan = RCLowPassMeasurementPlanner().from_observed_design(design, 100.0)

        self.assertIs(RCDesignContextSource.OBSERVED_DESIGN, plan.design_context_source)
        self.assertIs(RCNodeRoleKind.VIN, plan.vin_role.role)
        self.assertEqual(design.topology.input_node.ref, plan.vin_role.design_object)
        self.assertEqual(design.topology.output_node.ref, plan.vout_role.design_object)
        self.assertEqual(design.topology.reference_node.ref, plan.reference_role.design_object)
        self.assertEqual((1, 2), (plan.vin_channel, plan.vout_channel))
        self.assertEqual(100.0, plan.requested_frequency_hz)

    def test_user_declared_plan_preserves_distinct_provenance(self) -> None:
        plan = RCLowPassMeasurementPlanner().from_user_declared_design(
            requested_frequency_hz=100.0,
            vin="input node",
            vout="filter output",
            reference="circuit ground",
        )
        self.assertIs(RCDesignContextSource.USER_DECLARED_DESIGN_CONTEXT, plan.design_context_source)
        self.assertTrue(all(role.design_object is None for role in plan.roles))
        self.assertEqual(
            ("input node", "filter output", "circuit ground"),
            tuple(role.declared_label for role in plan.roles),
        )

    def test_plan_contains_no_physical_or_execution_authority(self) -> None:
        names = {item.name.casefold() for item in fields(RCLowPassMeasurementPlan)}
        for forbidden in ("scope", "confirmation", "authorization", "execute", "ipc"):
            self.assertFalse(any(forbidden in name for name in names))


class RCSinglePointAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = RCLowPassMeasurementPlanner().from_user_declared_design(
            requested_frequency_hz=100.0,
            vin="Vin",
            vout="Vout",
            reference="GND",
        )
        self.analyzer = RCSinglePointMeasurementAnalyzer()

    def analyze(self, **overrides) -> RCFrequencyPointMeasurement:
        inputs = {
            "vin_frequency": result(MeasurementKind.FREQUENCY, 1, 100.0),
            "vout_frequency": result(MeasurementKind.FREQUENCY, 2, 99.9),
            "vin_vpp": result(MeasurementKind.VPP, 1, 2.0),
            "vout_vpp": result(MeasurementKind.VPP, 2, 1.0),
        }
        inputs.update(overrides)
        return self.analyzer.analyze(self.plan, **inputs)

    def test_valid_physical_results_produce_deterministic_gain(self) -> None:
        measured = self.analyze()
        self.assertEqual(100.0, measured.requested_frequency_hz)
        self.assertEqual((100.0, 99.9), (measured.vin.frequency_hz, measured.vout.frequency_hz))
        self.assertEqual((2.0, 1.0), (measured.vin.vpp_v, measured.vout.vpp_v))
        self.assertEqual(0.5, measured.gain_ratio)
        self.assertAlmostEqual(-6.020599913, measured.gain_db)
        self.assertEqual(0.0, measured.vin_frequency_relative_deviation)
        self.assertAlmostEqual(0.001, measured.vout_frequency_relative_deviation)
        self.assertIs(RCEvidenceSource.PHYSICAL_MEASUREMENT, measured.vin.source)
        self.assertIs(RCEvidenceSource.SOFTWARE_ANALYSIS, measured.analysis_source)
        self.assertIsNone(measured.within_tolerance)

    def test_zero_vin_is_rejected(self) -> None:
        with self.assertRaisesRegex(RCMeasurementAnalysisError, "vin_vpp_not_positive"):
            self.analyze(vin_vpp=result(MeasurementKind.VPP, 1, 0.0))

    def test_missing_or_wrong_channel_result_is_rejected(self) -> None:
        with self.assertRaisesRegex(RCMeasurementAnalysisError, "measurement_missing"):
            self.analyze(vout_vpp=None)
        with self.assertRaisesRegex(RCMeasurementAnalysisError, "channel_mismatch"):
            self.analyze(vout_frequency=result(MeasurementKind.FREQUENCY, 1, 99.9))

    def test_targetless_plan_omits_deviation_but_keeps_gain(self) -> None:
        # A plan without a declared frequency target yields no deviation metric;
        # target-independent quantities (frequencies, Vpp, gain) still compute.
        targetless_plan = RCLowPassMeasurementPlanner().from_user_declared_design(
            requested_frequency_hz=None,
            vin="Vin",
            vout="Vout",
            reference="GND",
        )
        measured = self.analyzer.analyze(
            targetless_plan,
            vin_frequency=result(MeasurementKind.FREQUENCY, 1, 10020.04),
            vout_frequency=result(MeasurementKind.FREQUENCY, 2, 10020.04),
            vin_vpp=result(MeasurementKind.VPP, 1, 0.408),
            vout_vpp=result(MeasurementKind.VPP, 2, 4.12),
        )
        self.assertIsNone(measured.requested_frequency_hz)
        self.assertIsNone(measured.vin_frequency_relative_deviation)
        self.assertIsNone(measured.vout_frequency_relative_deviation)
        self.assertAlmostEqual(4.12 / 0.408, measured.gain_ratio)
        self.assertAlmostEqual(20.0 * math.log10(4.12 / 0.408), measured.gain_db)

    def test_non_finite_or_non_physical_observation_is_rejected(self) -> None:
        invalid = result(MeasurementKind.FREQUENCY, 1, 100.0)
        object.__setattr__(invalid.instrument_frequency, "value", math.nan)
        with self.assertRaisesRegex(RCMeasurementAnalysisError, "measurement_not_finite"):
            self.analyze(vin_frequency=invalid)

        # Simulated-backend observations are analyzable; a genuinely
        # non-physical provenance (software analysis claiming to be a
        # measurement) must still fail closed.
        software = result(MeasurementKind.VPP, 2, 1.0)
        object.__setattr__(software.instrument_vpp, "source", ObservationSource.SOFTWARE_ANALYSIS)
        with self.assertRaisesRegex(RCMeasurementAnalysisError, "measurement_not_physical"):
            self.analyze(vout_vpp=software)

    def test_wrong_metric_or_failed_measurement_is_rejected(self) -> None:
        with self.assertRaisesRegex(RCMeasurementAnalysisError, "measurement_kind_mismatch"):
            self.analyze(vin_frequency=result(MeasurementKind.VPP, 1, 2.0))
        failed = result(MeasurementKind.VPP, 2, 1.0)
        object.__setattr__(failed, "quality", MeasurementQuality.FAILED)
        with self.assertRaisesRegex(RCMeasurementAnalysisError, "measurement_failed"):
            self.analyze(vout_vpp=failed)

    def test_optional_waveform_artifacts_remain_opaque_and_channel_bound(self) -> None:
        measured = self.analyze(
            vin_waveform=waveform_result(1),
            vout_waveform=waveform_result(2),
        )
        self.assertEqual(1, len(measured.vin.artifacts))
        self.assertEqual(1, len(measured.vout.artifacts))
        self.assertNotEqual(
            measured.vin.artifacts[0].artifact_id,
            measured.vout.artifacts[0].artifact_id,
        )
        with self.assertRaisesRegex(RCMeasurementAnalysisError, "channel_mismatch"):
            self.analyze(vin_waveform=waveform_result(2))


if __name__ == "__main__":
    unittest.main()
