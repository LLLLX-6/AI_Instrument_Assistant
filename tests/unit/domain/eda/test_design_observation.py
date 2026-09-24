from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from ai_instrument_assistant.domain.eda import (
    CircuitComponent,
    CircuitComponentKind,
    CircuitPin,
    DesignDocument,
    DesignFingerprint,
    DesignNet,
    DesignObjectKind,
    DesignObjectRef,
    DesignObservation,
    DomainInvariantError,
)


SNAPSHOT = UUID("11111111-1111-4111-8111-111111111111")


def ref(kind: DesignObjectKind, identity: str) -> DesignObjectRef:
    return DesignObjectRef(
        provider="test-eda",
        object_type=kind,
        document_id="doc-1",
        snapshot_id=SNAPSHOT,
        native_id=identity,
        canonical_id=f"test-eda:{kind.value}:{identity}",
        display_name=identity,
    )


def document() -> DesignDocument:
    return DesignDocument(
        document_ref=ref(DesignObjectKind.DOCUMENT, "doc-1"),
        project_id="project-1",
        project_name="RC_Experiment",
        document_name="main",
        document_type="schematic",
        native_revision=None,
        fingerprint=DesignFingerprint(
            value="sha256:" + "a" * 64,
            scope_kind="full_design_observation",
            scope_version="1.0",
            included_paths=("document", "components", "nets"),
        ),
        is_dirty=False,
        captured_at=datetime(2026, 9, 13, tzinfo=UTC),
    )


class DesignObservationTests(unittest.TestCase):
    def test_full_design_is_provider_neutral_and_snapshot_coherent(self) -> None:
        input_net = DesignNet(ref(DesignObjectKind.NET, "n-in"), is_reference=False)
        output_net = DesignNet(ref(DesignObjectKind.NET, "n-out"), is_reference=False)
        resistor = CircuitComponent(
            ref=ref(DesignObjectKind.COMPONENT, "r1"),
            kind=CircuitComponentKind.RESISTOR,
            designator="R1",
            value_text="159.155 kOhm",
            pins=(
                CircuitPin("1", "1", input_net.ref),
                CircuitPin("2", "2", output_net.ref),
            ),
        )

        observed = DesignObservation(document(), (resistor,), (input_net, output_net))

        self.assertEqual("test-eda", observed.document.document_ref.provider)
        self.assertEqual(output_net.ref, observed.components[0].pins[1].net_ref)

    def test_cross_snapshot_pin_net_is_rejected(self) -> None:
        foreign = replace(
            ref(DesignObjectKind.NET, "foreign"),
            snapshot_id=UUID("22222222-2222-4222-8222-222222222222"),
        )
        component = CircuitComponent(
            ref=ref(DesignObjectKind.COMPONENT, "r1"),
            kind=CircuitComponentKind.RESISTOR,
            designator="R1",
            value_text="1 kOhm",
            pins=(CircuitPin("1", "1", foreign),),
        )

        with self.assertRaises(DomainInvariantError):
            DesignObservation(document(), (component,), ())


if __name__ == "__main__":
    unittest.main()
