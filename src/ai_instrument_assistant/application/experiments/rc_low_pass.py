from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5

from ai_instrument_assistant.application.ports.eda_interface import (
    EDAInterface,
    EDAInterfaceError,
)
from ai_instrument_assistant.domain.eda import (
    CircuitComponent,
    CircuitComponentKind,
    DesignNet,
    DesignObservation,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    DesignEvidenceContext,
    DesignEvidenceItem,
    DesignEvidenceKind,
    DesignEvidenceOrigin,
    Quantity,
    VerificationState,
)


class RCExperimentReadiness(StrEnum):
    DESIGN_NOT_OBSERVED = "DESIGN_NOT_OBSERVED"
    DESIGN_NOT_RECOGNIZED = "DESIGN_NOT_RECOGNIZED"
    DESIGN_AMBIGUOUS = "DESIGN_AMBIGUOUS"
    DESIGN_READY_FOR_MEASUREMENT = "DESIGN_READY_FOR_MEASUREMENT"


@dataclass(frozen=True, slots=True)
class RCFilterExperimentSpec:
    target_cutoff_hz: float
    source_resistance_ohm: float | None = None
    load_resistance_ohm: float | None = None
    relative_tolerance: float | None = None
    experiment_type: str = "RC_LOW_PASS"

    def __post_init__(self) -> None:
        if self.experiment_type != "RC_LOW_PASS":
            raise ValueError("only RC_LOW_PASS is supported")
        for name in ("target_cutoff_hz", "source_resistance_ohm", "load_resistance_ohm"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0
            ):
                raise ValueError(f"{name} must be a positive finite number")
            if value is not None:
                object.__setattr__(self, name, float(value))
        if self.relative_tolerance is not None:
            tolerance = self.relative_tolerance
            if (
                isinstance(tolerance, bool)
                or not isinstance(tolerance, (int, float))
                or not math.isfinite(tolerance)
                or tolerance < 0
            ):
                raise ValueError("relative_tolerance must be finite and non-negative")
            object.__setattr__(self, "relative_tolerance", float(tolerance))


@dataclass(frozen=True, slots=True)
class RCLowPassTopology:
    resistor: CircuitComponent
    capacitor: CircuitComponent
    input_node: DesignNet
    output_node: DesignNet
    reference_node: DesignNet


@dataclass(frozen=True, slots=True)
class RCExperimentResult:
    readiness: RCExperimentReadiness
    reason_codes: tuple[str, ...]
    topology: RCLowPassTopology | None = None
    candidate_refs: tuple[str, ...] = ()
    resistance_ohm: float | None = None
    effective_resistance_ohm: float | None = None
    capacitance_f: float | None = None
    calculated_cutoff_hz: float | None = None
    target_cutoff_hz: float | None = None
    relative_error: float | None = None
    within_tolerance: bool | None = None
    assumptions: tuple[str, ...] = ()
    design_evidence: DesignEvidenceContext | None = None


class RCLowPassTheory:
    _VALUE = re.compile(
        r"^\s*(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*"
        r"(?P<prefix>[pnumkKMµu]?)\s*(?P<unit>ohms?|Ω|f)?\s*$",
        re.IGNORECASE,
    )
    _PREFIX = {
        "": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6,
        "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6,
    }

    @staticmethod
    def cutoff_hz(resistance_ohm: float, capacitance_f: float) -> float:
        resistance = _positive(resistance_ohm, "resistance_ohm")
        capacitance = _positive(capacitance_f, "capacitance_f")
        return 1.0 / (2.0 * math.pi * resistance * capacitance)

    @staticmethod
    def resistance_ohm(target_cutoff_hz: float, capacitance_f: float) -> float:
        return 1.0 / (2.0 * math.pi * _positive(target_cutoff_hz, "target_cutoff_hz") * _positive(capacitance_f, "capacitance_f"))

    @staticmethod
    def capacitance_f(target_cutoff_hz: float, resistance_ohm: float) -> float:
        return 1.0 / (2.0 * math.pi * _positive(target_cutoff_hz, "target_cutoff_hz") * _positive(resistance_ohm, "resistance_ohm"))

    @staticmethod
    def magnitude(frequency_hz: float, cutoff_hz: float) -> float:
        frequency = _positive(frequency_hz, "frequency_hz")
        cutoff = _positive(cutoff_hz, "cutoff_hz")
        return 1.0 / math.sqrt(1.0 + (frequency / cutoff) ** 2)

    def parse_resistance_ohm(self, text: str) -> float:
        return self._parse(text, expected="resistance")

    def parse_capacitance_f(self, text: str) -> float:
        return self._parse(text, expected="capacitance")

    def _parse(self, text: str, *, expected: str) -> float:
        if not isinstance(text, str) or len(text) > 128:
            raise ValueError("component value must be bounded text")
        match = self._VALUE.fullmatch(text)
        if match is None:
            raise ValueError("component value has unsupported syntax")
        unit = (match.group("unit") or "").lower()
        if expected == "resistance" and unit == "f":
            raise ValueError("resistance value cannot use farads")
        if expected == "capacitance" and unit not in ("", "f"):
            raise ValueError("capacitance value cannot use ohms")
        value = float(match.group("number")) * self._PREFIX[match.group("prefix")]
        return _positive(value, "component value")


class RCLowPassExperimentService:
    def __init__(self, eda: EDAInterface, theory: RCLowPassTheory | None = None) -> None:
        self._eda = eda
        self._theory = theory or RCLowPassTheory()

    async def evaluate(self, spec: RCFilterExperimentSpec) -> RCExperimentResult:
        try:
            observation = await self._eda.observe_design()
        except EDAInterfaceError:
            return RCExperimentResult(
                readiness=RCExperimentReadiness.DESIGN_NOT_OBSERVED,
                reason_codes=("design_observation_unavailable",),
                target_cutoff_hz=spec.target_cutoff_hz,
            )

        candidates, reasons = self._recognize(observation)
        if not candidates:
            return RCExperimentResult(
                readiness=RCExperimentReadiness.DESIGN_NOT_RECOGNIZED,
                reason_codes=reasons,
                target_cutoff_hz=spec.target_cutoff_hz,
            )
        if len(candidates) != 1:
            return RCExperimentResult(
                readiness=RCExperimentReadiness.DESIGN_AMBIGUOUS,
                reason_codes=("multiple_rc_low_pass_candidates",),
                candidate_refs=tuple(
                    f"{candidate.resistor.ref.canonical_id}|{candidate.capacitor.ref.canonical_id}"
                    for candidate in candidates
                ),
                target_cutoff_hz=spec.target_cutoff_hz,
            )

        topology = candidates[0]
        try:
            resistance = self._theory.parse_resistance_ohm(topology.resistor.value_text or "")
            capacitance = self._theory.parse_capacitance_f(topology.capacitor.value_text or "")
        except ValueError:
            return RCExperimentResult(
                readiness=RCExperimentReadiness.DESIGN_NOT_RECOGNIZED,
                reason_codes=("component_value_invalid",),
                topology=topology,
                target_cutoff_hz=spec.target_cutoff_hz,
            )
        series_resistance = resistance + (spec.source_resistance_ohm or 0.0)
        effective_resistance = series_resistance
        if spec.load_resistance_ohm is not None:
            effective_resistance = (
                series_resistance * spec.load_resistance_ohm
                / (series_resistance + spec.load_resistance_ohm)
            )
        cutoff = self._theory.cutoff_hz(effective_resistance, capacitance)
        relative_error = abs(cutoff - spec.target_cutoff_hz) / spec.target_cutoff_hz
        within = None if spec.relative_tolerance is None else relative_error <= spec.relative_tolerance
        assumptions = (
            "ideal_first_order_rc_low_pass",
            "source_resistance_excluded" if spec.source_resistance_ohm is None else "explicit_source_resistance_applied",
            "load_resistance_excluded" if spec.load_resistance_ohm is None else "explicit_resistive_load_applied",
        )
        evidence = self._evidence(observation, topology, spec, resistance, capacitance, cutoff, relative_error)
        return RCExperimentResult(
            readiness=RCExperimentReadiness.DESIGN_READY_FOR_MEASUREMENT,
            reason_codes=("recognized_unique_rc_low_pass",),
            topology=topology,
            resistance_ohm=resistance,
            effective_resistance_ohm=effective_resistance,
            capacitance_f=capacitance,
            calculated_cutoff_hz=cutoff,
            target_cutoff_hz=spec.target_cutoff_hz,
            relative_error=relative_error,
            within_tolerance=within,
            assumptions=assumptions,
            design_evidence=evidence,
        )

    @staticmethod
    def _recognize(observation: DesignObservation) -> tuple[list[RCLowPassTopology], tuple[str, ...]]:
        resistors = [item for item in observation.components if item.kind is CircuitComponentKind.RESISTOR]
        capacitors = [item for item in observation.components if item.kind is CircuitComponentKind.CAPACITOR]
        if not resistors:
            return [], ("missing_resistor",)
        if not capacitors:
            return [], ("missing_capacitor",)
        net_by_ref = {item.ref: item for item in observation.nets}
        candidates: list[RCLowPassTopology] = []
        for resistor in resistors:
            resistor_nets = _two_distinct_nets(resistor)
            if resistor_nets is None:
                continue
            for capacitor in capacitors:
                capacitor_nets = _two_distinct_nets(capacitor)
                if capacitor_nets is None:
                    continue
                shared = set(resistor_nets) & set(capacitor_nets)
                reference = [item for item in capacitor_nets if net_by_ref[item].is_reference]
                if len(shared) != 1 or len(reference) != 1 or reference[0] in shared:
                    continue
                output_ref = next(iter(shared))
                input_ref = next(item for item in resistor_nets if item != output_ref)
                candidates.append(RCLowPassTopology(
                    resistor=resistor,
                    capacitor=capacitor,
                    input_node=net_by_ref[input_ref],
                    output_node=net_by_ref[output_ref],
                    reference_node=net_by_ref[reference[0]],
                ))
        return candidates, (() if candidates else ("topology_not_rc_low_pass",))

    @staticmethod
    def _evidence(
        observation: DesignObservation,
        topology: RCLowPassTopology,
        spec: RCFilterExperimentSpec,
        resistance: float,
        capacitance: float,
        cutoff: float,
        relative_error: float,
    ) -> DesignEvidenceContext:
        data = (
            ("observed_resistance", Quantity(resistance, "ohm"), "ohm", topology.resistor.ref, DesignEvidenceKind.DOCUMENT_FACT, DesignEvidenceOrigin.DESIGN_DERIVED),
            ("observed_capacitance", Quantity(capacitance, "F"), "F", topology.capacitor.ref, DesignEvidenceKind.DOCUMENT_FACT, DesignEvidenceOrigin.DESIGN_DERIVED),
            ("target_cutoff", Quantity(spec.target_cutoff_hz, "Hz"), "Hz", None, DesignEvidenceKind.TARGET_DECLARATION, DesignEvidenceOrigin.USER_STATEMENT),
            ("calculated_theoretical_cutoff", Quantity(cutoff, "Hz"), "Hz", None, DesignEvidenceKind.CONNECTIVITY_FACT, DesignEvidenceOrigin.DESIGN_DERIVED),
            ("target_relative_deviation", relative_error, None, None, DesignEvidenceKind.CONNECTIVITY_FACT, DesignEvidenceOrigin.DESIGN_DERIVED),
            ("input_node", topology.input_node.ref.canonical_id, None, topology.input_node.ref, DesignEvidenceKind.CONNECTIVITY_FACT, DesignEvidenceOrigin.DESIGN_DERIVED),
            ("output_node", topology.output_node.ref.canonical_id, None, topology.output_node.ref, DesignEvidenceKind.CONNECTIVITY_FACT, DesignEvidenceOrigin.DESIGN_DERIVED),
            ("reference_node", topology.reference_node.ref.canonical_id, None, topology.reference_node.ref, DesignEvidenceKind.CONNECTIVITY_FACT, DesignEvidenceOrigin.DESIGN_DERIVED),
        )
        items = tuple(
            DesignEvidenceItem(
                evidence_id=uuid5(NAMESPACE_URL, f"re001:{observation.snapshot_id}:{label}"),
                kind=kind, label=label, value=value, unit=unit,
                document=observation.document, design_object=design_object,
                verification_state=VerificationState.SNAPSHOT_BOUNDED,
                observed_at=observation.document.captured_at, origin=origin,
            )
            for label, value, unit, design_object, kind, origin in data
        )
        return DesignEvidenceContext(document=observation.document, evidence=items)


def _two_distinct_nets(component: CircuitComponent) -> tuple[object, object] | None:
    refs = tuple(pin.net_ref for pin in component.pins if pin.net_ref is not None)
    if len(refs) != 2 or refs[0] == refs[1]:
        return None
    return refs[0], refs[1]


def _positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return normalized
