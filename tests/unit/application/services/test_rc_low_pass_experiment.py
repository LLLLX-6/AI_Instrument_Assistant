from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime
from uuid import UUID

from ai_instrument_assistant.application.experiments.rc_low_pass import (
    RCFilterExperimentSpec,
    RCExperimentReadiness,
    RCLowPassExperimentService,
    RCLowPassTheory,
)
from ai_instrument_assistant.application.ports.eda_interface import (
    EDACapability,
    EDACapabilitySet,
    EDAInterface,
    EDAInterfaceError,
)
from ai_instrument_assistant.domain.eda import (
    CircuitComponent,
    CircuitComponentKind,
    CircuitPin,
    DesignDocument,
    DesignNet,
    DesignObjectKind,
    DesignObjectRef,
    DesignObservation,
)


SNAPSHOT = UUID("11111111-1111-4111-8111-111111111111")


def ref(kind: DesignObjectKind, identity: str, label: str | None = None) -> DesignObjectRef:
    return DesignObjectRef(
        provider="recorded-eda", object_type=kind, document_id="doc-rc",
        snapshot_id=SNAPSHOT, native_id=identity,
        canonical_id=f"recorded-eda:{kind.value}:{identity}",
        display_name=label,
    )


def rc_observation(*, labels=("A", "B", "C"), duplicate=False) -> DesignObservation:
    nets = (
        DesignNet(ref(DesignObjectKind.NET, "n1", labels[0]), False),
        DesignNet(ref(DesignObjectKind.NET, "n2", labels[1]), False),
        DesignNet(ref(DesignObjectKind.NET, "n0", labels[2]), True),
    )
    parts = [
        CircuitComponent(
            ref(DesignObjectKind.COMPONENT, "r1", "not-an-identity"),
            CircuitComponentKind.RESISTOR, "R1", "159.155 kOhm",
            (CircuitPin("1", "1", nets[0].ref), CircuitPin("2", "2", nets[1].ref)),
        ),
        CircuitComponent(
            ref(DesignObjectKind.COMPONENT, "c1", "also-presentation-only"),
            CircuitComponentKind.CAPACITOR, "C1", "1 nF",
            (CircuitPin("1", "1", nets[1].ref), CircuitPin("2", "2", nets[2].ref)),
        ),
    ]
    if duplicate:
        parts.extend((
            CircuitComponent(
                ref(DesignObjectKind.COMPONENT, "r2"), CircuitComponentKind.RESISTOR,
                "R2", "159.155 kOhm",
                (CircuitPin("1", "1", nets[0].ref), CircuitPin("2", "2", nets[1].ref)),
            ),
            CircuitComponent(
                ref(DesignObjectKind.COMPONENT, "c2"), CircuitComponentKind.CAPACITOR,
                "C2", "1 nF",
                (CircuitPin("1", "1", nets[1].ref), CircuitPin("2", "2", nets[2].ref)),
            ),
        ))
    doc = DesignDocument(
        ref(DesignObjectKind.DOCUMENT, "doc-rc"), "p", "RC", "main", "schematic",
        None, None, False, datetime(2026, 9, 13, tzinfo=UTC),
    )
    return DesignObservation(doc, tuple(parts), nets)


class RecordedEDA(EDAInterface):
    def __init__(self, observation: DesignObservation | Exception) -> None:
        self.observation = observation
        self.selection_reads = 0

    @property
    def capabilities(self) -> EDACapabilitySet:
        return EDACapabilitySet(frozenset({EDACapability.DESIGN_READ}))

    async def observe_design(self) -> DesignObservation:
        if isinstance(self.observation, Exception):
            raise self.observation
        return self.observation

    async def get_active_document(self):  # pragma: no cover - forbidden path
        raise AssertionError("RE-001A must use full-design observation")

    async def get_selection(self):  # pragma: no cover - forbidden path
        self.selection_reads += 1
        raise AssertionError("RE-001A must not read UI selection")

    async def highlight(self, command):  # pragma: no cover - forbidden path
        raise AssertionError("RE-001A is read-only")


class RCTheoryTests(unittest.TestCase):
    def test_deterministic_rc_calculations_and_magnitude(self) -> None:
        theory = RCLowPassTheory()
        cutoff = theory.cutoff_hz(1_000.0, 159.154943e-9)
        self.assertAlmostEqual(1_000.0, cutoff, places=5)
        self.assertAlmostEqual(1_000.0, theory.resistance_ohm(1_000.0, 159.154943e-9), places=5)
        self.assertAlmostEqual(159.154943e-9, theory.capacitance_f(1_000.0, 1_000.0), places=14)
        self.assertAlmostEqual(1 / math.sqrt(2), theory.magnitude(1_000.0, cutoff), places=7)

    def test_component_value_parsing_is_typed_and_bounded(self) -> None:
        theory = RCLowPassTheory()
        self.assertEqual(10_000.0, theory.parse_resistance_ohm("10 kOhm"))
        self.assertAlmostEqual(100e-9, theory.parse_capacitance_f("100 nF"))
        for invalid in ("", "ten k", "-1 kOhm", "1 bananas"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                theory.parse_resistance_ohm(invalid)


class RCExperimentTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_design_is_recognized_without_ui_selection(self) -> None:
        eda = RecordedEDA(rc_observation(labels=("foo", "bar", "earth")))
        result = await RCLowPassExperimentService(eda).evaluate(
            RCFilterExperimentSpec(target_cutoff_hz=1_000.0)
        )

        self.assertIs(result.readiness, RCExperimentReadiness.DESIGN_READY_FOR_MEASUREMENT)
        self.assertEqual("r1", result.topology.resistor.ref.native_id)
        self.assertEqual("c1", result.topology.capacitor.ref.native_id)
        self.assertEqual("n1", result.topology.input_node.ref.native_id)
        self.assertEqual("n2", result.topology.output_node.ref.native_id)
        self.assertEqual("n0", result.topology.reference_node.ref.native_id)
        self.assertAlmostEqual(1_000.0, result.calculated_cutoff_hz, places=3)
        self.assertIsNone(result.within_tolerance)
        self.assertEqual(0, eda.selection_reads)
        self.assertGreaterEqual(len(result.design_evidence.evidence), 5)

    async def test_labels_and_component_order_do_not_define_topology(self) -> None:
        observation = rc_observation(labels=("Vout", "Vin", "not-gnd"))
        reordered = DesignObservation(
            observation.document,
            tuple(reversed(observation.components)),
            tuple(reversed(observation.nets)),
        )
        result = await RCLowPassExperimentService(RecordedEDA(reordered)).evaluate(
            RCFilterExperimentSpec(1_000.0)
        )
        self.assertEqual("n1", result.topology.input_node.ref.native_id)
        self.assertEqual("n2", result.topology.output_node.ref.native_id)
        self.assertEqual("n0", result.topology.reference_node.ref.native_id)

    async def test_multiple_candidates_are_reported_not_silently_chosen(self) -> None:
        result = await RCLowPassExperimentService(RecordedEDA(rc_observation(duplicate=True))).evaluate(
            RCFilterExperimentSpec(1_000.0)
        )
        self.assertIs(result.readiness, RCExperimentReadiness.DESIGN_AMBIGUOUS)
        self.assertEqual(4, len(result.candidate_refs))
        self.assertIsNone(result.topology)

    async def test_missing_or_wrong_topology_is_bounded(self) -> None:
        observation = rc_observation()
        no_cap = DesignObservation(observation.document, observation.components[:1], observation.nets)
        result = await RCLowPassExperimentService(RecordedEDA(no_cap)).evaluate(
            RCFilterExperimentSpec(1_000.0)
        )
        self.assertIs(result.readiness, RCExperimentReadiness.DESIGN_NOT_RECOGNIZED)
        self.assertIn("missing_capacitor", result.reason_codes)

        no_resistor = DesignObservation(observation.document, observation.components[1:], observation.nets)
        result = await RCLowPassExperimentService(RecordedEDA(no_resistor)).evaluate(
            RCFilterExperimentSpec(1_000.0)
        )
        self.assertIn("missing_resistor", result.reason_codes)

        capacitor = observation.components[1]
        wrong_capacitor = CircuitComponent(
            capacitor.ref, capacitor.kind, capacitor.designator, capacitor.value_text,
            (CircuitPin("1", "1", observation.nets[0].ref), CircuitPin("2", "2", observation.nets[1].ref)),
        )
        wrong = DesignObservation(
            observation.document, (observation.components[0], wrong_capacitor), observation.nets
        )
        result = await RCLowPassExperimentService(RecordedEDA(wrong)).evaluate(
            RCFilterExperimentSpec(1_000.0)
        )
        self.assertEqual(("topology_not_rc_low_pass",), result.reason_codes)

    async def test_explicit_source_and_load_resistance_are_applied(self) -> None:
        result = await RCLowPassExperimentService(RecordedEDA(rc_observation())).evaluate(
            RCFilterExperimentSpec(1_000.0, source_resistance_ohm=1_000.0, load_resistance_ohm=1_000_000.0)
        )
        expected = (159_155.0 + 1_000.0) * 1_000_000.0 / (160_155.0 + 1_000_000.0)
        self.assertAlmostEqual(expected, result.effective_resistance_ohm)
        self.assertIn("explicit_source_resistance_applied", result.assumptions)
        self.assertIn("explicit_resistive_load_applied", result.assumptions)

    async def test_result_is_immutable_and_model_has_no_fact_override_surface(self) -> None:
        result = await RCLowPassExperimentService(RecordedEDA(rc_observation())).evaluate(
            RCFilterExperimentSpec(1_000.0)
        )
        with self.assertRaises((AttributeError, TypeError)):
            result.calculated_cutoff_hz = 42.0  # type: ignore[misc]
        self.assertFalse(hasattr(result, "model_claims"))

    async def test_provider_failure_remains_structured(self) -> None:
        result = await RCLowPassExperimentService(
            RecordedEDA(EDAInterfaceError("provider details"))
        ).evaluate(RCFilterExperimentSpec(1_000.0))
        self.assertIs(result.readiness, RCExperimentReadiness.DESIGN_NOT_OBSERVED)
        self.assertEqual(("design_observation_unavailable",), result.reason_codes)
        self.assertNotIn("provider details", repr(result))


if __name__ == "__main__":
    unittest.main()
