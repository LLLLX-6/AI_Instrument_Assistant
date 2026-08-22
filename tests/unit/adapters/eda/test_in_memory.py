from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from ai_instrument_assistant.adapters.eda.in_memory import InMemoryEDAAdapter
from ai_instrument_assistant.application.ports.eda_interface import (
    CapabilityUnsupportedError,
    EDACapability,
    EDACapabilitySet,
    EDAInterface,
    HighlightCommand,
    HighlightStatus,
    HighlightStyle,
    StaleDesignSnapshotError,
)


NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)


def highlight_command(adapter: InMemoryEDAAdapter, *, key: str = "highlight-1") -> HighlightCommand:
    document = adapter.active_document
    assert document is not None
    target = adapter.selection_context.selection.primary_object
    assert target is not None
    return HighlightCommand(
        document_ref=document.document_ref,
        expected_snapshot_id=document.snapshot_id,
        expected_content_fingerprint=document.content_fingerprint,
        expected_fingerprint_scope_kind=document.fingerprint_scope_kind,
        expected_fingerprint_scope_version=document.fingerprint_scope_version,
        expected_fingerprint_scope=document.fingerprint_scope,
        targets=(target,),
        style=HighlightStyle.ANALYSIS,
        ttl=timedelta(seconds=30),
        replace_existing=True,
        idempotency_key=key,
    )


class InMemoryEDAAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_pwm_out_scenario_exposes_document_and_context(self) -> None:
        adapter = InMemoryEDAAdapter.for_pwm_out_scenario(clock=lambda: NOW)

        document = await adapter.get_active_document()
        context = await adapter.get_selection()

        self.assertEqual(document.project_name, "STM32_Test")
        self.assertEqual(document.document_name, "main_schematic")
        self.assertEqual(context.selection.primary_object.display_name, "PWM_OUT")
        self.assertEqual(context.nets[0].source.component_reference, "U1")
        self.assertEqual(context.nets[0].source.pin_name, "PA0")
        self.assertEqual(context.nets[0].signal_expectation.frequency_hz, 10_000.0)
        self.assertEqual(context.nets[0].signal_expectation.duty_cycle.percent, 30.0)

    async def test_empty_selection_is_supported(self) -> None:
        adapter = InMemoryEDAAdapter.for_pwm_out_scenario(clock=lambda: NOW)
        adapter.set_empty_selection()

        context = await adapter.get_selection()

        self.assertEqual(context.selection.selected_objects, ())
        self.assertIsNone(context.selection.primary_object)
        self.assertEqual(context.nets, ())

    async def test_valid_highlight_is_applied_and_recorded(self) -> None:
        adapter = InMemoryEDAAdapter.for_pwm_out_scenario(clock=lambda: NOW)
        command = highlight_command(adapter)

        result = await adapter.highlight(command)

        self.assertEqual(result.status, HighlightStatus.APPLIED)
        self.assertEqual(result.applied_targets, command.targets)
        self.assertEqual(result.expires_at, NOW + timedelta(seconds=30))
        self.assertEqual(adapter.highlight_history, (command,))

    async def test_duplicate_idempotency_key_is_noop_without_new_history(self) -> None:
        adapter = InMemoryEDAAdapter.for_pwm_out_scenario(clock=lambda: NOW)
        command = highlight_command(adapter)
        await adapter.highlight(command)

        result = await adapter.highlight(command)

        self.assertEqual(result.status, HighlightStatus.NOOP)
        self.assertEqual(result.applied_targets, ())
        self.assertTrue(result.warnings)
        self.assertEqual(adapter.highlight_history, (command,))

    async def test_stale_highlight_has_no_side_effects(self) -> None:
        adapter = InMemoryEDAAdapter.for_pwm_out_scenario(clock=lambda: NOW)
        command = highlight_command(adapter)
        adapter.advance_snapshot(
            UUID("22222222-2222-4222-8222-222222222222"),
            content_fingerprint="sha256:new-snapshot",
        )

        with self.assertRaises(StaleDesignSnapshotError):
            await adapter.highlight(command)

        self.assertEqual(adapter.highlight_history, ())

    async def test_unsupported_highlight_has_no_side_effects(self) -> None:
        adapter = InMemoryEDAAdapter.for_pwm_out_scenario(
            capabilities=EDACapabilitySet(
                frozenset(
                    {
                        EDACapability.DOCUMENT_READ,
                        EDACapability.SELECTION_READ,
                    }
                )
            ),
            clock=lambda: NOW,
        )

        with self.assertRaises(CapabilityUnsupportedError):
            await adapter.highlight(highlight_command(adapter))

        self.assertEqual(adapter.highlight_history, ())

    def test_adapter_implements_the_async_eda_port(self) -> None:
        adapter = InMemoryEDAAdapter.for_pwm_out_scenario(clock=lambda: NOW)

        self.assertIsInstance(adapter, EDAInterface)
        self.assertTrue(inspect.iscoroutinefunction(adapter.get_active_document))
        self.assertTrue(inspect.iscoroutinefunction(adapter.get_selection))
        self.assertTrue(inspect.iscoroutinefunction(adapter.highlight))


if __name__ == "__main__":
    unittest.main()
