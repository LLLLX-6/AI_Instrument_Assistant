from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from ai_instrument_assistant.application.ports.eda_interface import (
    EDACapability,
    EDACapabilitySet,
    EDAInterface,
    EDANotConnectedError,
    HighlightCommand,
    HighlightResult,
    InconsistentDesignObservationError,
)
from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    DesignSelectionCandidateIdentity,
    TrustedDesignSelectionResolutionStatus,
    build_candidate_set_binding,
    issue_trusted_design_selection_decision,
    resolve_trusted_design_selection,
)
from ai_instrument_assistant.application.services.eda_design_evidence import (
    DesignEvidenceProjectionStatus,
    EDADesignEvidenceCaptureService,
    ProjectionDiagnosticReason,
    ProjectionResolutionStage,
    create_user_provided_numeric_target,
    diagnose_selection_projection,
)
from ai_instrument_assistant.domain.eda.models import (
    CircuitNet,
    DesignDocument,
    DesignFingerprint,
    DesignObjectKind,
    DesignObjectRef,
    DesignSelection,
    ProbeTargetKind,
    SelectionContext,
)
from ai_instrument_assistant.domain.engineering_evidence import (
    DesignEvidenceKind,
    DesignEvidenceOrigin,
    EngineeringMetric,
    EvidenceCategory,
    Quantity,
    TargetProvenance,
    VerificationState,
)


NOW = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
DOCUMENT_SNAPSHOT = UUID("10101010-1010-4010-8010-101010101010")
SELECTION_SNAPSHOT = UUID("20202020-2020-4020-8020-202020202020")
REAL_DIAGNOSTIC_FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "jlceda"
    / "phase8b2-real-ambiguous-wire-component-selection.json"
)


class FakeEDA(EDAInterface):
    def __init__(self, document: DesignDocument, selection: SelectionContext) -> None:
        self.document = document
        self.selection = selection
        self.calls: list[str] = []
        self.failure: Exception | None = None

    @property
    def capabilities(self) -> EDACapabilitySet:
        return EDACapabilitySet(
            frozenset({EDACapability.DOCUMENT_READ, EDACapability.SELECTION_READ})
        )

    async def get_active_document(self) -> DesignDocument:
        self.calls.append("document")
        if self.failure is not None:
            raise self.failure
        return self.document

    async def get_selection(self) -> SelectionContext:
        self.calls.append("selection")
        return self.selection

    async def highlight(self, command: HighlightCommand) -> HighlightResult:
        raise AssertionError("Phase 8B.2 capture must remain read-only")


def document() -> DesignDocument:
    return DesignDocument(
        document_ref=DesignObjectRef(
            provider="jlceda-pro",
            object_type=DesignObjectKind.DOCUMENT,
            document_id="main-document",
            snapshot_id=DOCUMENT_SNAPSHOT,
            native_id="main-document",
            canonical_id="jlceda-pro:document:main-document",
            display_name=None,
        ),
        project_id="STM32_Test",
        project_name=None,
        document_name=None,
        document_type="schematic",
        native_revision="provider-revision-from-another-observation",
        fingerprint=DesignFingerprint(
            value="sha256:bounded",
            scope_kind="document_projection",
            scope_version="1",
            included_paths=("document",),
        ),
        is_dirty=False,
        captured_at=NOW,
    )


def selection_context(
    *,
    selected_kind: DesignObjectKind = DesignObjectKind.WIRE,
    selected_name: str | None = "PWM_OUT",
    include_net: bool = True,
    selected_count: int = 1,
) -> SelectionContext:
    doc_ref = replace(document().document_ref, snapshot_id=SELECTION_SNAPSHOT)
    selected = tuple(
        DesignObjectRef(
            provider="jlceda-pro",
            object_type=selected_kind,
            document_id=doc_ref.document_id,
            snapshot_id=SELECTION_SNAPSHOT,
            native_id=f"primitive-{index}",
            canonical_id=f"jlceda-pro:{selected_kind.value}:primitive-{index}",
            display_name=selected_name,
            provider_kind={
                DesignObjectKind.WIRE: "Wire",
                DesignObjectKind.COMPONENT: "Component",
            }.get(selected_kind, selected_kind.value),
        )
        for index in range(selected_count)
    )
    nets = ()
    if include_net:
        net_ref = DesignObjectRef(
            provider="jlceda-pro",
            object_type=DesignObjectKind.NET,
            document_id=doc_ref.document_id,
            snapshot_id=SELECTION_SNAPSHOT,
            native_id=None,
            canonical_id="jlceda-pro:net:PWM_OUT",
            display_name="PWM_OUT",
            provider_kind="Wire.net",
        )
        nets = (CircuitNet(ref=net_ref, endpoints=()),)
    return SelectionContext(
        selection=DesignSelection(document_ref=doc_ref, selected_objects=selected),
        nets=nets,
    )


class EDADesignEvidenceCaptureTests(unittest.IsolatedAsyncioTestCase):
    def test_recorded_real_wire_component_shape_remains_fail_closed(self) -> None:
        fixture = json.loads(REAL_DIAGNOSTIC_FIXTURE.read_text(encoding="utf-8"))
        doc_ref = replace(document().document_ref, snapshot_id=SELECTION_SNAPSHOT)
        selected = tuple(
            DesignObjectRef(
                provider="jlceda-pro",
                object_type=DesignObjectKind(item["object_type"]),
                document_id=doc_ref.document_id,
                snapshot_id=SELECTION_SNAPSHOT,
                native_id=item["native_id"],
                canonical_id=item["canonical_id"],
                display_name=item["display_name"],
                provider_kind=item["provider_kind"],
            )
            for item in fixture["selected_objects"]
        )
        net_item = fixture["derived_nets"][0]
        net = CircuitNet(
            ref=DesignObjectRef(
                provider="jlceda-pro",
                object_type=DesignObjectKind(net_item["object_type"]),
                document_id=doc_ref.document_id,
                snapshot_id=SELECTION_SNAPSHOT,
                native_id=net_item["native_id"],
                canonical_id=net_item["canonical_id"],
                display_name=net_item["display_name"],
                provider_kind=net_item["provider_kind"],
            ),
            endpoints=(),
        )
        context = SelectionContext(
            selection=DesignSelection(document_ref=doc_ref, selected_objects=selected),
            nets=(net,),
        )

        diagnostic = diagnose_selection_projection(context)
        expected = fixture["expected_diagnostic"]

        self.assertEqual(diagnostic.selection_count, fixture["selection_count"])
        self.assertEqual(list(diagnostic.provider_kinds), fixture["provider_kinds"])
        self.assertEqual(
            diagnostic.projected_candidate_count,
            expected["projected_candidate_count"],
        )
        self.assertEqual(
            [kind.value for kind in diagnostic.projected_candidate_kinds],
            expected["projected_candidate_kinds"],
        )
        self.assertEqual(diagnostic.reason.value, expected["ambiguity_reason"])
        self.assertEqual(diagnostic.resolution_stage.value, expected["resolution_stage"])
        self.assertEqual(diagnostic.scope_expansion.value, expected["scope_expansion"])
        self.assertTrue(diagnostic.is_ambiguous)

        initial = EDADesignEvidenceCaptureService.project(
            active_document=document(),
            selection_context=context,
            observed_at=NOW,
        )
        self.assertEqual(initial.status, DesignEvidenceProjectionStatus.AMBIGUOUS_SELECTION)
        self.assertIsNone(initial.probe_target)

    def test_trusted_wire_decision_projects_without_mutating_provider_selection(self) -> None:
        fixture = json.loads(REAL_DIAGNOSTIC_FIXTURE.read_text(encoding="utf-8"))
        doc_ref = replace(document().document_ref, snapshot_id=SELECTION_SNAPSHOT)
        selected = tuple(
            DesignObjectRef(
                provider="jlceda-pro",
                object_type=DesignObjectKind(item["object_type"]),
                document_id=doc_ref.document_id,
                snapshot_id=SELECTION_SNAPSHOT,
                native_id=item["native_id"],
                canonical_id=item["canonical_id"],
                display_name=item["display_name"],
                provider_kind=item["provider_kind"],
            )
            for item in fixture["selected_objects"]
        )
        net_item = fixture["derived_nets"][0]
        net = CircuitNet(
            ref=DesignObjectRef(
                provider="jlceda-pro",
                object_type=DesignObjectKind.NET,
                document_id=doc_ref.document_id,
                snapshot_id=SELECTION_SNAPSHOT,
                native_id=net_item["native_id"],
                canonical_id=net_item["canonical_id"],
                display_name=net_item["display_name"],
                provider_kind=net_item["provider_kind"],
            ),
            endpoints=(),
        )
        context = SelectionContext(
            selection=DesignSelection(
                document_ref=doc_ref,
                selected_objects=selected,
                primary_object=None,
            ),
            nets=(net,),
        )
        candidate_binding = build_candidate_set_binding(
            selection_context=context,
            selection_observed_at=NOW,
        )
        wire = next(item for item in selected if item.object_type is DesignObjectKind.WIRE)
        decision = issue_trusted_design_selection_decision(
            decision_id=UUID("91919191-9191-4191-8191-919191919191"),
            candidate_binding=candidate_binding,
            selected_candidate=DesignSelectionCandidateIdentity.from_ref(wire),
            workflow_id="phase8b2-real-jlceda-recorded",
            request_correlation_id="phase8b2-request-1",
            decided_at=NOW,
        )
        resolution = resolve_trusted_design_selection(
            current_selection=context,
            current_binding=candidate_binding,
            decision=decision,
            trusted_workflow_id="phase8b2-real-jlceda-recorded",
            trusted_request_correlation_id="phase8b2-request-1",
        )

        projection = EDADesignEvidenceCaptureService.project(
            active_document=document(),
            selection_context=context,
            observed_at=NOW,
            trusted_resolution=resolution,
        )

        self.assertEqual(resolution.status, TrustedDesignSelectionResolutionStatus.RESOLVED)
        self.assertEqual(projection.status, DesignEvidenceProjectionStatus.PROJECTED)
        self.assertEqual(projection.trusted_selection_resolution, resolution)
        self.assertEqual(projection.source_object, wire)
        self.assertEqual(projection.probe_target.design_object, net.ref)
        self.assertEqual(
            projection.design_context.selection.selection.selected_objects,
            selected,
        )
        self.assertIsNone(projection.design_context.selection.selection.primary_object)

    def test_diagnostic_distinguishes_selected_wire_from_derived_net_candidate(self) -> None:
        diagnostic = diagnose_selection_projection(selection_context())

        self.assertEqual(diagnostic.selection_count, 1)
        self.assertEqual(diagnostic.provider_kinds, ("Wire",))
        self.assertEqual(diagnostic.derived_net_count, 1)
        self.assertEqual(diagnostic.projected_candidate_count, 1)
        self.assertEqual(diagnostic.projected_candidate_kinds, (DesignObjectKind.NET,))
        self.assertEqual(
            diagnostic.reason,
            ProjectionDiagnosticReason.WIRE_TO_SINGLE_DERIVED_NET,
        )
        self.assertEqual(
            diagnostic.resolution_stage,
            ProjectionResolutionStage.RESOLVED,
        )
        self.assertEqual(diagnostic.scope_expansion, "wire_to_net")
        self.assertFalse(diagnostic.is_ambiguous)

    def test_diagnostic_reports_multiple_provider_selections_before_resolution(self) -> None:
        diagnostic = diagnose_selection_projection(selection_context(selected_count=2))

        self.assertEqual(diagnostic.selection_count, 2)
        self.assertEqual(diagnostic.provider_kinds, ("Wire", "Wire"))
        self.assertEqual(diagnostic.derived_net_count, 1)
        self.assertEqual(diagnostic.projected_candidate_count, 1)
        self.assertEqual(diagnostic.projected_candidate_kinds, (DesignObjectKind.NET,))
        self.assertEqual(
            diagnostic.reason,
            ProjectionDiagnosticReason.MULTIPLE_SELECTED_OBJECTS,
        )
        self.assertEqual(
            diagnostic.resolution_stage,
            ProjectionResolutionStage.SELECTION_CARDINALITY,
        )
        self.assertTrue(diagnostic.is_ambiguous)

    def test_diagnostic_does_not_promote_unsupported_object_to_candidate(self) -> None:
        diagnostic = diagnose_selection_projection(
            selection_context(
                selected_kind=DesignObjectKind.COMPONENT,
                selected_name="U1",
                include_net=False,
            )
        )

        self.assertEqual(diagnostic.projected_candidate_count, 0)
        self.assertEqual(
            diagnostic.reason,
            ProjectionDiagnosticReason.UNSUPPORTED_SELECTED_OBJECT,
        )
        self.assertEqual(
            diagnostic.resolution_stage,
            ProjectionResolutionStage.SELECTED_OBJECT_KIND,
        )
        self.assertFalse(diagnostic.is_ambiguous)

    async def test_real_style_wire_selection_projects_bounded_design_fact_and_probe(self) -> None:
        eda = FakeEDA(document(), selection_context())
        service = EDADesignEvidenceCaptureService(eda=eda, clock=lambda: NOW)

        first = await service.capture()
        second = await service.capture()

        self.assertEqual(eda.calls, ["document", "selection", "document", "selection"])
        self.assertEqual(first.status, DesignEvidenceProjectionStatus.PROJECTED)
        self.assertEqual(first.active_document.snapshot_id, DOCUMENT_SNAPSHOT)
        self.assertEqual(first.design_context.document.snapshot_id, SELECTION_SNAPSHOT)
        self.assertIsNone(first.design_context.document.native_revision)
        self.assertIsNone(first.design_context.document.fingerprint)
        self.assertIsNone(first.design_context.document.is_dirty)
        self.assertEqual(first.probe_target, second.probe_target)
        self.assertEqual(first.probe_target.kind, ProbeTargetKind.DESIGN_ONLY)
        self.assertIsNone(first.probe_target.physical_location)
        self.assertEqual(first.probe_target.design_object.display_name, "PWM_OUT")
        self.assertEqual(first.source_object.object_type, DesignObjectKind.WIRE)
        self.assertEqual(
            {item.kind for item in first.design_context.evidence},
            {DesignEvidenceKind.DOCUMENT_FACT, DesignEvidenceKind.CONNECTIVITY_FACT},
        )
        self.assertTrue(
            all(item.category is EvidenceCategory.DESIGN_FACT for item in first.design_context.evidence)
        )
        self.assertTrue(
            all(item.origin is DesignEvidenceOrigin.DESIGN_DERIVED for item in first.design_context.evidence)
        )
        self.assertTrue(
            all(item.verification_state is VerificationState.SNAPSHOT_BOUNDED for item in first.design_context.evidence)
        )
        self.assertTrue(
            all(not isinstance(item.value, Quantity) for item in first.design_context.evidence),
            "structural selection must not invent an electrical target",
        )

    async def test_empty_selection_preserves_document_but_creates_no_probe(self) -> None:
        result = await EDADesignEvidenceCaptureService(
            eda=FakeEDA(document(), selection_context(include_net=False, selected_count=0)),
            clock=lambda: NOW,
        ).capture()
        self.assertEqual(result.status, DesignEvidenceProjectionStatus.EMPTY_SELECTION)
        self.assertIsNone(result.source_object)
        self.assertIsNone(result.probe_target)
        self.assertEqual(len(result.design_context.evidence), 1)

    async def test_unsupported_component_selection_does_not_invent_probe(self) -> None:
        result = await EDADesignEvidenceCaptureService(
            eda=FakeEDA(
                document(),
                selection_context(
                    selected_kind=DesignObjectKind.COMPONENT,
                    selected_name="U1",
                    include_net=False,
                ),
            ),
            clock=lambda: NOW,
        ).capture()
        self.assertEqual(result.status, DesignEvidenceProjectionStatus.UNSUPPORTED_SELECTION)
        self.assertIsNone(result.probe_target)

    async def test_ambiguous_selection_does_not_choose_by_name(self) -> None:
        result = await EDADesignEvidenceCaptureService(
            eda=FakeEDA(document(), selection_context(selected_count=2)),
            clock=lambda: NOW,
        ).capture()
        self.assertEqual(result.status, DesignEvidenceProjectionStatus.AMBIGUOUS_SELECTION)
        self.assertIsNone(result.probe_target)

    async def test_document_identity_change_fails_instead_of_relabeling_observations(self) -> None:
        selection = selection_context()
        other_ref = replace(
            selection.selection.document_ref,
            document_id="other-document",
            canonical_id="jlceda-pro:document:other-document",
        )
        other_objects = tuple(
            replace(selected, document_id="other-document")
            for selected in selection.selection.selected_objects
        )
        other_selection = replace(
            selection,
            selection=replace(
                selection.selection,
                document_ref=other_ref,
                selected_objects=other_objects,
            ),
            nets=tuple(replace(net, ref=replace(net.ref, document_id="other-document")) for net in selection.nets),
        )
        with self.assertRaisesRegex(
            InconsistentDesignObservationError,
            "document identity",
        ):
            await EDADesignEvidenceCaptureService(
                eda=FakeEDA(document(), other_selection), clock=lambda: NOW
            ).capture()

    async def test_provider_failure_has_no_fixture_fallback(self) -> None:
        eda = FakeEDA(document(), selection_context())
        eda.failure = EDANotConnectedError("offline")
        with self.assertRaises(EDANotConnectedError):
            await EDADesignEvidenceCaptureService(eda=eda, clock=lambda: NOW).capture()
        self.assertEqual(eda.calls, ["document"])

    async def test_user_target_factory_never_claims_schematic_derivation(self) -> None:
        projection = await EDADesignEvidenceCaptureService(
            eda=FakeEDA(document(), selection_context()), clock=lambda: NOW
        ).capture()
        declaration = create_user_provided_numeric_target(
            evidence_id=UUID("30303030-3030-4030-8030-303030303030"),
            target_id=UUID("40404040-4040-4040-8040-404040404040"),
            document=projection.design_context.document,
            design_object=projection.probe_target.design_object,
            observed_at=NOW,
            label="PWM_OUT expected frequency",
            metric=EngineeringMetric.FREQUENCY,
            value=10.0,
            unit="kHz",
            tolerance=None,
        )
        self.assertEqual(declaration.evidence.origin, DesignEvidenceOrigin.USER_STATEMENT)
        self.assertEqual(declaration.evidence.verification_state, VerificationState.USER_ASSERTED)
        self.assertEqual(declaration.target.provenance, TargetProvenance.USER_PROVIDED)
        self.assertEqual(declaration.target.source_evidence_ids, (declaration.evidence.evidence_id,))


if __name__ == "__main__":
    unittest.main()
