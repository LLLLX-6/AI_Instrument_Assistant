from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from uuid import UUID

from ai_instrument_assistant.domain.eda.errors import DomainInvariantError
from ai_instrument_assistant.domain.eda.models import (
    ArtifactReference,
    CircuitEndpoint,
    CircuitNet,
    DesignFingerprint,
    DesignDocument,
    DesignObjectKind,
    DesignObjectRef,
    DesignSelection,
    DutyCycle,
    MeasurementContext,
    ProbeConnectionConfirmation,
    ProbeTarget,
    ProbeTargetKind,
    SelectionContext,
    SignalExpectation,
)


SNAPSHOT_A = UUID("11111111-1111-4111-8111-111111111111")
SNAPSHOT_B = UUID("22222222-2222-4222-8222-222222222222")
CONTEXT_ID = UUID("33333333-3333-4333-8333-333333333333")
TARGET_ID = UUID("44444444-4444-4444-8444-444444444444")
CONFIRMATION_ID = UUID("55555555-5555-4555-8555-555555555555")
ARTIFACT_ID = UUID("66666666-6666-4666-8666-666666666666")


def document_ref(
    snapshot_id: UUID = SNAPSHOT_A,
    provider: str = "kicad",
) -> DesignObjectRef:
    return DesignObjectRef(
        provider=provider,
        object_type=DesignObjectKind.DOCUMENT,
        document_id="main-schematic",
        snapshot_id=snapshot_id,
        native_id="sheet-root",
        canonical_id=f"{provider}:project:main-schematic:document",
        display_name="main_schematic",
    )


def net_ref(
    snapshot_id: UUID = SNAPSHOT_A,
    provider: str = "kicad",
) -> DesignObjectRef:
    return DesignObjectRef(
        provider=provider,
        object_type=DesignObjectKind.NET,
        document_id="main-schematic",
        snapshot_id=snapshot_id,
        native_id="net-pwm-out",
        canonical_id=f"{provider}:project:main-schematic:net:pwm-out",
        display_name="PWM_OUT",
    )


def design_document(snapshot_id: UUID = SNAPSHOT_A) -> DesignDocument:
    return DesignDocument(
        document_ref=document_ref(snapshot_id),
        project_id="stm32-test",
        project_name="STM32_Test",
        document_name="main_schematic",
        document_type="schematic",
        native_revision=None,
        fingerprint=DesignFingerprint(
            value="sha256:" + "a" * 64,
            scope_kind="normalized-document-projection",
            scope_version="1.0",
            included_paths=("project_id", "document_name", "document_type"),
        ),
        is_dirty=False,
        captured_at=datetime(2026, 8, 22, 10, 0, tzinfo=UTC),
    )


def selection(snapshot_id: UUID = SNAPSHOT_A) -> DesignSelection:
    selected_net = net_ref(snapshot_id)
    return DesignSelection(
        document_ref=document_ref(snapshot_id),
        selected_objects=(selected_net,),
        primary_object=selected_net,
    )


def probe_target(snapshot_id: UUID = SNAPSHOT_A) -> ProbeTarget:
    return ProbeTarget(
        target_id=TARGET_ID,
        design_object=net_ref(snapshot_id),
        kind=ProbeTargetKind.DESIGN_ONLY,
    )


class DesignIdentityTests(unittest.TestCase):
    def test_selection_object_kinds_include_wire_component_and_other(self) -> None:
        self.assertEqual("wire", DesignObjectKind.WIRE.value)
        self.assertEqual("component", DesignObjectKind.COMPONENT.value)
        self.assertEqual("other", DesignObjectKind.OTHER.value)

    def test_provider_kind_is_retained_but_optional(self) -> None:
        wire = DesignObjectRef(
            provider="jlceda-pro",
            object_type=DesignObjectKind.WIRE,
            document_id="document-1",
            snapshot_id=SNAPSHOT_A,
            native_id="primitive-1",
            canonical_id="jlceda-pro:wire:document-1:primitive-1",
            display_name="PWM_OUT",
            provider_kind="Wire",
        )
        self.assertEqual("Wire", wire.provider_kind)
        self.assertIsNone(net_ref().provider_kind)

    def test_design_object_ref_is_provider_neutral_and_immutable(self) -> None:
        reference = net_ref(provider="altium")

        self.assertEqual("altium", reference.provider)
        self.assertNotEqual("jlceda-pro", reference.provider)
        with self.assertRaises(FrozenInstanceError):
            reference.provider = "jlceda-pro"  # type: ignore[misc]

    def test_document_keeps_revision_snapshot_and_fingerprint_separate(self) -> None:
        document = design_document()

        self.assertIsNone(document.native_revision)
        self.assertEqual(SNAPSHOT_A, document.snapshot_id)
        self.assertEqual("sha256:" + "a" * 64, document.fingerprint.value)
        self.assertEqual("normalized-document-projection", document.fingerprint.scope_kind)
        self.assertEqual("1.0", document.fingerprint.scope_version)
        self.assertEqual(
            ("project_id", "document_name", "document_type"),
            document.fingerprint.included_paths,
        )

    def test_provider_unknown_document_metadata_is_explicitly_optional(self) -> None:
        reference = DesignObjectRef(
            provider="jlceda-pro",
            object_type=DesignObjectKind.DOCUMENT,
            document_id="official-document-uuid",
            snapshot_id=SNAPSHOT_A,
            native_id="official-document-uuid",
            canonical_id="jlceda-pro:document:official-document-uuid",
            display_name=None,
        )
        document = DesignDocument(
            document_ref=reference,
            project_id=None,
            project_name=None,
            document_name=None,
            document_type="pcb",
            native_revision=None,
            fingerprint=None,
            is_dirty=None,
            captured_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
        )

        self.assertIsNone(document.document_ref.display_name)
        self.assertIsNone(document.project_id)
        self.assertIsNone(document.project_name)
        self.assertIsNone(document.document_name)
        self.assertIsNone(document.fingerprint)
        self.assertIsNone(document.is_dirty)

    def test_design_fingerprint_is_complete_and_immutable(self) -> None:
        fingerprint = DesignFingerprint(
            value="sha256:" + "c" * 64,
            scope_kind="normalized-document-projection",
            scope_version="1.0",
            included_paths=("document_ref.document_id",),
        )

        with self.assertRaises(FrozenInstanceError):
            fingerprint.value = "sha256:" + "d" * 64  # type: ignore[misc]
        with self.assertRaises(DomainInvariantError):
            DesignFingerprint(
                value="sha256:" + "c" * 64,
                scope_kind="normalized-document-projection",
                scope_version="1.0",
                included_paths=(),
            )

    def test_snapshot_is_an_aia_observation_token_not_a_content_version(self) -> None:
        self.assertIn("observation token", DesignDocument.__doc__ or "")
        document = DesignDocument(
            document_ref=document_ref(),
            project_id=None,
            project_name=None,
            document_name=None,
            document_type="schematic",
            native_revision=None,
            fingerprint=None,
            is_dirty=None,
            captured_at=datetime(2026, 9, 5, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(SNAPSHOT_A, document.snapshot_id)
        self.assertIsNone(document.native_revision)
        self.assertIsNone(document.fingerprint)

    def test_tab_id_is_not_a_domain_field(self) -> None:
        self.assertNotIn("tab_id", {field.name for field in fields(DesignDocument)})
        self.assertNotIn("tab_id", {field.name for field in fields(DesignObjectRef)})


class DesignSelectionTests(unittest.TestCase):
    def test_objects_from_different_snapshots_cannot_form_one_selection(self) -> None:
        with self.assertRaises(DomainInvariantError):
            DesignSelection(
                document_ref=document_ref(SNAPSHOT_A),
                selected_objects=(net_ref(SNAPSHOT_B),),
            )

    def test_empty_selection_is_valid(self) -> None:
        empty_selection = DesignSelection(document_ref=document_ref())

        self.assertEqual((), empty_selection.selected_objects)
        self.assertIsNone(empty_selection.primary_object)

    def test_primary_object_must_belong_to_selected_objects(self) -> None:
        selected_net = net_ref()
        different_net = DesignObjectRef(
            provider="kicad",
            object_type=DesignObjectKind.NET,
            document_id="main-schematic",
            snapshot_id=SNAPSHOT_A,
            native_id="net-other",
            canonical_id="kicad:project:main-schematic:net:other",
            display_name="OTHER",
        )

        with self.assertRaises(DomainInvariantError):
            DesignSelection(
                document_ref=document_ref(),
                selected_objects=(selected_net,),
                primary_object=different_net,
            )


class CircuitModelTests(unittest.TestCase):
    def test_empty_net_endpoints_mean_unresolved_connectivity(self) -> None:
        net = CircuitNet(ref=net_ref(), endpoints=(), source=None)

        self.assertEqual((), net.endpoints)
        self.assertTrue(net.connectivity_unresolved)
        self.assertIn("unresolved connectivity", CircuitNet.__doc__ or "")

    def test_source_is_rejected_when_empty_endpoints_are_unresolved(self) -> None:
        with self.assertRaises(DomainInvariantError):
            CircuitNet(
                ref=net_ref(),
                endpoints=(),
                source=CircuitEndpoint(component_reference="U1", pin_name="PA0"),
            )

    def test_derived_net_need_not_be_a_selected_primitive(self) -> None:
        selected_wire = DesignObjectRef(
            provider="kicad",
            object_type=DesignObjectKind.WIRE,
            document_id="main-schematic",
            snapshot_id=SNAPSHOT_A,
            native_id="wire-1",
            canonical_id="kicad:wire:main-schematic:wire-1",
            display_name="PWM_OUT",
            provider_kind="Wire",
        )
        context = SelectionContext(
            selection=DesignSelection(
                document_ref=document_ref(),
                selected_objects=(selected_wire,),
            ),
            nets=(CircuitNet(ref=net_ref(), endpoints=()),),
        )

        self.assertNotIn(context.nets[0].ref, context.selection.selected_objects)

    def test_derived_net_must_share_selection_observation(self) -> None:
        with self.assertRaises(DomainInvariantError):
            SelectionContext(
                selection=DesignSelection(document_ref=document_ref(SNAPSHOT_A)),
                nets=(CircuitNet(ref=net_ref(SNAPSHOT_B), endpoints=()),),
            )

    def test_duty_cycle_has_ratio_canonical_form_and_explicit_percent_view(self) -> None:
        cases = (
            (DutyCycle.from_percent(0.0), 0.0, 0.0),
            (DutyCycle.from_percent(30.0), 0.30, 30.0),
            (DutyCycle.from_ratio(1.0), 1.0, 100.0),
        )

        for duty_cycle, ratio, percent in cases:
            with self.subTest(percent=percent):
                self.assertAlmostEqual(ratio, duty_cycle.ratio)
                self.assertAlmostEqual(percent, duty_cycle.percent)

    def test_duty_cycle_rejects_out_of_range_ratio_and_percent(self) -> None:
        invalid_factories = (
            lambda: DutyCycle.from_ratio(-0.001),
            lambda: DutyCycle.from_ratio(1.001),
            lambda: DutyCycle.from_percent(-0.01),
            lambda: DutyCycle.from_percent(100.01),
        )

        for factory in invalid_factories:
            with self.subTest(factory=factory):
                with self.assertRaises(DomainInvariantError):
                    factory()

    def test_signal_expectation_rejects_bare_float_duty_cycle(self) -> None:
        with self.assertRaises(DomainInvariantError):
            SignalExpectation(
                frequency_hz=10_000.0,
                duty_cycle=0.30,  # type: ignore[arg-type]
            )

    def test_pwm_net_can_capture_source_endpoint_and_expectation(self) -> None:
        source = CircuitEndpoint(component_reference="U1", pin_name="PA0")
        expectation = SignalExpectation(
            frequency_hz=10_000.0,
            duty_cycle=DutyCycle.from_percent(30.0),
        )
        net = CircuitNet(
            ref=net_ref(),
            endpoints=(source,),
            source=source,
            signal_expectation=expectation,
        )

        self.assertEqual("U1", net.source.component_reference)
        self.assertEqual("PA0", net.source.pin_name)
        self.assertEqual(0.30, net.signal_expectation.duty_cycle.ratio)
        self.assertEqual(30.0, net.signal_expectation.duty_cycle.percent)

    def test_selection_context_keeps_selection_and_circuit_context_separate(self) -> None:
        selected_net = net_ref()
        design_selection = DesignSelection(
            document_ref=document_ref(),
            selected_objects=(selected_net,),
            primary_object=selected_net,
        )
        source = CircuitEndpoint(component_reference="U1", pin_name="PA0")
        net = CircuitNet(
            ref=selected_net,
            endpoints=(source,),
            source=source,
            signal_expectation=SignalExpectation(
                frequency_hz=10_000.0,
                duty_cycle=DutyCycle.from_ratio(0.30),
            ),
        )

        context = SelectionContext(selection=design_selection, nets=(net,))

        self.assertIs(design_selection, context.selection)
        self.assertEqual((net,), context.nets)
        self.assertNotIn("nets", {field.name for field in fields(DesignSelection)})


class ProbeAndMeasurementTests(unittest.TestCase):
    def test_design_only_probe_target_needs_no_physical_location(self) -> None:
        target = probe_target()

        self.assertIsNone(target.physical_location)

    def test_user_confirmation_is_separate_from_probe_target(self) -> None:
        target = probe_target()
        confirmation = ProbeConnectionConfirmation(
            confirmation_id=CONFIRMATION_ID,
            probe_target_id=target.target_id,
            snapshot_id=SNAPSHOT_A,
            confirmed_at=datetime(2026, 8, 22, 10, 5, tzinfo=UTC),
            confirmed_by="user",
        )

        target_field_names = {field.name for field in fields(ProbeTarget)}
        self.assertNotIn("confirmed", target_field_names)
        self.assertNotIn("connection_confirmation", target_field_names)
        self.assertEqual(target.target_id, confirmation.probe_target_id)

    def test_measurement_context_rejects_mixed_snapshots(self) -> None:
        with self.assertRaises(DomainInvariantError):
            MeasurementContext(
                context_id=CONTEXT_ID,
                document=design_document(SNAPSHOT_A),
                selection=selection(SNAPSHOT_B),
                probe_target=probe_target(SNAPSHOT_A),
            )

    def test_measurement_context_rejects_probe_target_from_another_snapshot(self) -> None:
        with self.assertRaises(DomainInvariantError):
            MeasurementContext(
                context_id=CONTEXT_ID,
                document=design_document(SNAPSHOT_A),
                selection=selection(SNAPSHOT_A),
                probe_target=probe_target(SNAPSHOT_B),
            )

    def test_measurement_context_rejects_stale_connection_confirmation(self) -> None:
        confirmation = ProbeConnectionConfirmation(
            confirmation_id=CONFIRMATION_ID,
            probe_target_id=TARGET_ID,
            snapshot_id=SNAPSHOT_B,
            confirmed_at=datetime(2026, 8, 22, 10, 5, tzinfo=UTC),
            confirmed_by="user",
        )

        with self.assertRaises(DomainInvariantError):
            MeasurementContext(
                context_id=CONTEXT_ID,
                document=design_document(SNAPSHOT_A),
                selection=selection(SNAPSHOT_A),
                probe_target=probe_target(SNAPSHOT_A),
                connection_confirmation=confirmation,
            )

    def test_measurement_context_references_independent_confirmation(self) -> None:
        confirmation = ProbeConnectionConfirmation(
            confirmation_id=CONFIRMATION_ID,
            probe_target_id=TARGET_ID,
            snapshot_id=SNAPSHOT_A,
            confirmed_at=datetime(2026, 8, 22, 10, 5, tzinfo=UTC),
            confirmed_by="user",
        )
        context = MeasurementContext(
            context_id=CONTEXT_ID,
            document=design_document(),
            selection=selection(),
            probe_target=probe_target(),
            connection_confirmation=confirmation,
        )

        self.assertIs(confirmation, context.connection_confirmation)

    def test_measurement_context_does_not_require_a_waveform(self) -> None:
        context = MeasurementContext(
            context_id=CONTEXT_ID,
            document=design_document(),
            selection=selection(),
            probe_target=probe_target(),
        )

        self.assertEqual((), context.evidence)
        self.assertEqual((), context.results)
        self.assertNotIn("waveform", {field.name for field in fields(MeasurementContext)})

    def test_measurement_context_accepts_generic_scalar_results(self) -> None:
        context = MeasurementContext(
            context_id=CONTEXT_ID,
            document=design_document(),
            selection=selection(),
            probe_target=probe_target(),
            results=(
                ("frequency_hz", 10_000.0),
                ("duty_cycle_percent", 30.0),
            ),
        )

        self.assertEqual(10_000.0, dict(context.results)["frequency_hz"])

    def test_measurement_context_rejects_embedded_large_result_values(self) -> None:
        with self.assertRaises(DomainInvariantError):
            MeasurementContext(
                context_id=CONTEXT_ID,
                document=design_document(),
                selection=selection(),
                probe_target=probe_target(),
                results=(("samples", [0.0, 1.0, 0.0]),),  # type: ignore[list-item]
            )

    def test_large_evidence_is_represented_by_artifact_reference(self) -> None:
        artifact = ArtifactReference(
            artifact_id=ARTIFACT_ID,
            uri="artifact://measurements/pwm-out-capture",
            media_type="application/vnd.aia.waveform+json",
            size_bytes=8_000_000,
            sha256="b" * 64,
        )
        context = MeasurementContext(
            context_id=CONTEXT_ID,
            document=design_document(),
            selection=selection(),
            probe_target=probe_target(),
            evidence=(artifact,),
        )

        self.assertEqual((artifact,), context.evidence)


if __name__ == "__main__":
    unittest.main()
