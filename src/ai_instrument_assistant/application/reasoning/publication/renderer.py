from __future__ import annotations

from ..models import ClaimForm, PublicationObligation
from .errors import PublicationBoundaryError, PublicationFailureCode
from .models import GroundedPublicationPlan, PublicationRenderAtom, PublicationSlot, RENDERER_VERSION


class DeterministicPublicationRenderer:
    """Finite reviewed English renderer; it never accepts candidate-authored prose."""

    version = RENDERER_VERSION

    def render(self, plan: GroundedPublicationPlan) -> str:
        if plan.renderer_version != self.version or not plan.slots:
            raise PublicationBoundaryError(PublicationFailureCode.RENDER_PLAN_INVALID)
        lines = tuple(self._render_slot(slot) for slot in plan.slots)
        result = "\n".join(lines)
        if len(result) > 16_384:
            raise PublicationBoundaryError(PublicationFailureCode.RENDER_PLAN_INVALID)
        return result

    def _render_slot(self, slot: PublicationSlot) -> str:
        permission, atom = slot.permission, slot.atom
        if not set(permission.obligations).issubset(set(slot.renderable_obligations)):
            raise PublicationBoundaryError(PublicationFailureCode.PUBLICATION_OBLIGATION_UNSATISFIED)
        form = permission.claim_form
        if form in (ClaimForm.EVIDENCE_VALUE, ClaimForm.EVIDENCE_AVAILABILITY, ClaimForm.TARGET_VALUE):
            return self._render_evidence(form, atom, permission.obligations)
        if form is ClaimForm.LIMITATION_RESTATEMENT:
            return self._render_limitation(atom)
        return self._render_comparison(form, atom)

    def _render_evidence(
        self,
        form: ClaimForm,
        atom: PublicationRenderAtom,
        obligations: tuple[PublicationObligation, ...],
    ) -> str:
        prefix = {
            "DESIGN_OBSERVATION": "Design observation",
            "USER_STATEMENT": "User-stated design context",
            "USER_TARGET": "User-provided target",
            "DESIGN_TARGET": "Design-derived target",
            "INSTRUMENT": "Instrument measurement",
            "SOFTWARE_ANALYSIS": "Software analysis",
            "SIMULATED": "Simulated evidence",
        }.get(atom.source)
        if prefix is None:
            raise PublicationBoundaryError(PublicationFailureCode.RENDER_PLAN_INVALID)
        if form is ClaimForm.EVIDENCE_AVAILABILITY or atom.value is None:
            line = f"{prefix}: {atom.label} is unavailable."
        else:
            line = f"{prefix}: {atom.label} = {_with_unit(atom.value, atom.unit)}."
        if PublicationObligation.PRESERVE_DEGRADED_QUALITY in obligations:
            line += " Quality: degraded."
        if PublicationObligation.INCLUDE_MATERIAL_WARNINGS in obligations:
            if not atom.warnings:
                raise PublicationBoundaryError(PublicationFailureCode.PUBLICATION_OBLIGATION_UNSATISFIED)
            line += " " + " ".join(f"Warning: {warning}" for warning in atom.warnings)
        if PublicationObligation.PRESERVE_SEQUENTIAL_COHERENCE in obligations:
            if atom.detail != "sequential_same_session":
                raise PublicationBoundaryError(PublicationFailureCode.PUBLICATION_OBLIGATION_UNSATISFIED)
            line += " Instrument and software observations were sequential in the same session, not simultaneous or atomic."
        if PublicationObligation.PRESERVE_OBSERVATION_IDENTITY_LIMIT in obligations:
            line += " This reflects the bounded design observation only and does not prove design immutability."
        return line

    @staticmethod
    def _render_limitation(atom: PublicationRenderAtom) -> str:
        if atom.source == "WARNING":
            return f"Warning: {atom.detail}."
        if atom.source == "QUALITY":
            return f"Overall evidence quality: {atom.detail}."
        if atom.source == "COHERENCE":
            if atom.detail == "sequential_same_session":
                return "Evidence coherence: instrument and software observations were sequential in the same session, not simultaneous or atomic."
            return f"Evidence coherence: {atom.detail}."
        if atom.source == "UNRESOLVED_QUESTION":
            return f"Unresolved question: {atom.detail}."
        return f"Limitation: {atom.detail}."

    @staticmethod
    def _render_comparison(form: ClaimForm, atom: PublicationRenderAtom) -> str:
        status, reason = atom.comparison_status, atom.comparison_reason
        if status is None or reason is None or atom.metric is None:
            raise PublicationBoundaryError(PublicationFailureCode.COMPARISON_SEMANTICS_MISMATCH)
        metric = atom.metric.lower().replace("_", " ")
        identity = f"Comparison for {metric}: status {status}; reason {reason}."
        if form is ClaimForm.COMPARISON_STATUS:
            if reason == "MEASUREMENT_MISSING":
                return f"Comparison for {metric} is indeterminate because the measurement is missing; reason MEASUREMENT_MISSING."
            return identity
        if form is ClaimForm.COMPARISON_DIFFERENCE:
            if atom.difference is None:
                raise PublicationBoundaryError(PublicationFailureCode.COMPARISON_SEMANTICS_MISMATCH)
            return f"Comparison for {metric}: deterministic difference = {atom.difference}; status {status}; reason {reason}."
        if form is ClaimForm.COMPLIANCE_UNDETERMINED:
            if status != "INDETERMINATE" or reason != "TOLERANCE_UNSPECIFIED":
                raise PublicationBoundaryError(PublicationFailureCode.COMPARISON_SEMANTICS_MISMATCH)
            return f"Compliance for {metric} cannot be determined because no explicit tolerance is available; status INDETERMINATE; reason TOLERANCE_UNSPECIFIED."
        if form is ClaimForm.WITHIN_SPECIFIED_CRITERION:
            if status != "MATCH" or reason not in {"WITHIN_TOLERANCE", "WITHIN_RANGE", "DISCRETE_EQUAL"}:
                raise PublicationBoundaryError(PublicationFailureCode.COMPARISON_SEMANTICS_MISMATCH)
            return f"The observed {metric} is within the specified tolerance; status {status}; reason {reason}."
        if form is ClaimForm.OUTSIDE_SPECIFIED_CRITERION:
            if status != "MISMATCH" or reason not in {"OUTSIDE_TOLERANCE", "OUTSIDE_RANGE", "DISCRETE_DIFFERENT"}:
                raise PublicationBoundaryError(PublicationFailureCode.COMPARISON_SEMANTICS_MISMATCH)
            return f"The observed {metric} is outside the specified tolerance; status {status}; reason {reason}."
        raise PublicationBoundaryError(PublicationFailureCode.RENDER_PLAN_INVALID)


def _with_unit(value: str, unit: str | None) -> str:
    return value if unit is None else f"{value} {unit}"
