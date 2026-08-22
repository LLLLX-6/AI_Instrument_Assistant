from __future__ import annotations

import inspect
import unittest
from datetime import timedelta
from typing import get_type_hints
from uuid import UUID

from ai_instrument_assistant.application.ports.eda_interface import (
    CapabilityUnsupportedError,
    DesignObjectNotFoundError,
    EDACapability,
    EDACapabilitySet,
    EDAInterface,
    EDAInterfaceError,
    HighlightCommand,
    HighlightResult,
    HighlightStatus,
    HighlightStyle,
    NoActiveDocumentError,
    OperationNotAllowedError,
    StaleDesignSnapshotError,
)
from ai_instrument_assistant.domain.eda.models import (
    DesignDocument,
    DesignObjectKind,
    DesignObjectRef,
    SelectionContext,
)


SNAPSHOT_ID = UUID("11111111-1111-4111-8111-111111111111")


def document_ref() -> DesignObjectRef:
    return DesignObjectRef(
        provider="kicad",
        object_type=DesignObjectKind.DOCUMENT,
        document_id="main-schematic",
        snapshot_id=SNAPSHOT_ID,
        native_id="sheet-root",
        canonical_id="kicad:project:main-schematic:document",
        display_name="main_schematic",
    )


def net_ref() -> DesignObjectRef:
    return DesignObjectRef(
        provider="kicad",
        object_type=DesignObjectKind.NET,
        document_id="main-schematic",
        snapshot_id=SNAPSHOT_ID,
        native_id="net-pwm-out",
        canonical_id="kicad:project:main-schematic:net:pwm-out",
        display_name="PWM_OUT",
    )


class EDAInterfaceTests(unittest.TestCase):
    def test_port_exposes_only_phase_three_operations(self) -> None:
        self.assertEqual(
            frozenset(
                {
                    "capabilities",
                    "get_active_document",
                    "get_selection",
                    "highlight",
                }
            ),
            EDAInterface.__abstractmethods__,
        )

    def test_capabilities_use_provider_neutral_semantic_names(self) -> None:
        self.assertEqual("document.read", EDACapability.DOCUMENT_READ.value)
        self.assertEqual("selection.read", EDACapability.SELECTION_READ.value)
        self.assertEqual("view.highlight", EDACapability.VIEW_HIGHLIGHT.value)

    def test_capability_set_is_immutable_and_can_require_a_capability(self) -> None:
        capabilities = EDACapabilitySet(
            supported=frozenset({EDACapability.DOCUMENT_READ})
        )

        self.assertTrue(capabilities.supports(EDACapability.DOCUMENT_READ))
        self.assertFalse(capabilities.supports(EDACapability.VIEW_HIGHLIGHT))
        with self.assertRaises(CapabilityUnsupportedError):
            capabilities.require(EDACapability.VIEW_HIGHLIGHT)

    def test_port_returns_domain_models_and_highlights_object_refs(self) -> None:
        active_hints = get_type_hints(EDAInterface.get_active_document)
        selection_hints = get_type_hints(EDAInterface.get_selection)
        highlight_hints = get_type_hints(EDAInterface.highlight)

        self.assertIs(DesignDocument, active_hints["return"])
        self.assertIs(SelectionContext, selection_hints["return"])
        self.assertIs(HighlightCommand, highlight_hints["command"])
        self.assertIs(HighlightResult, highlight_hints["return"])

    def test_remote_port_operations_are_explicitly_async(self) -> None:
        self.assertTrue(inspect.iscoroutinefunction(EDAInterface.get_active_document))
        self.assertTrue(inspect.iscoroutinefunction(EDAInterface.get_selection))
        self.assertTrue(inspect.iscoroutinefunction(EDAInterface.highlight))

    def test_port_signature_contains_no_primitive_identifier_operation(self) -> None:
        highlight_parameters = inspect.signature(EDAInterface.highlight).parameters

        self.assertEqual(("self", "command"), tuple(highlight_parameters))

    def test_highlight_command_carries_explicit_document_guard(self) -> None:
        target = net_ref()
        command = HighlightCommand(
            document_ref=document_ref(),
            expected_snapshot_id=SNAPSHOT_ID,
            expected_content_fingerprint="sha256:" + "a" * 64,
            expected_fingerprint_scope_kind="normalized-document-projection",
            expected_fingerprint_scope_version="1.0",
            expected_fingerprint_scope=("document_name", "document_type"),
            targets=(target,),
            style=HighlightStyle.ANALYSIS,
            ttl=timedelta(seconds=30),
            replace_existing=True,
            idempotency_key="highlight-pwm-out-1",
        )

        self.assertEqual(SNAPSHOT_ID, command.expected_snapshot_id)
        self.assertEqual((target,), command.targets)
        self.assertEqual(30, command.ttl.total_seconds())

    def test_highlight_result_distinguishes_applied_and_noop(self) -> None:
        applied = HighlightResult(
            status=HighlightStatus.APPLIED,
            applied_targets=(net_ref(),),
        )
        noop = HighlightResult(status=HighlightStatus.NOOP)

        self.assertTrue(applied.applied)
        self.assertFalse(applied.noop)
        self.assertTrue(noop.noop)
        self.assertEqual((), noop.applied_targets)

    def test_interface_errors_are_provider_neutral_categories(self) -> None:
        for error_type in (
            CapabilityUnsupportedError,
            NoActiveDocumentError,
            StaleDesignSnapshotError,
            DesignObjectNotFoundError,
            OperationNotAllowedError,
        ):
            with self.subTest(error=error_type.__name__):
                self.assertTrue(issubclass(error_type, EDAInterfaceError))


if __name__ == "__main__":
    unittest.main()
