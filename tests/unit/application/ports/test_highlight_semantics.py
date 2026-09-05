from __future__ import annotations
import unittest
from dataclasses import replace
from ai_instrument_assistant.application.ports.eda_interface import (
    HighlightCommand, HighlightResult, GuardMode, ScopeExpansion,
    SubmissionStatus, VerificationStatus, HighlightStyle, OperationNotAllowedError,
)
from ai_instrument_assistant.adapters.eda.in_memory import InMemoryEDAAdapter

class HighlightSemanticTests(unittest.IsolatedAsyncioTestCase):
    def command(self):
        adapter = InMemoryEDAAdapter.for_pwm_out_scenario()
        return adapter, HighlightCommand(
            document_ref=adapter.active_document.document_ref,
            expected_snapshot_id=adapter.active_document.snapshot_id,
            targets=adapter.selection_context.selection.selected_objects,
            idempotency_key="semantic-1",
        )

    def test_defaults_express_strong_guard_and_unrequested_presentation(self):
        _, command = self.command()
        self.assertIs(command.guard_mode, GuardMode.STRONG_REQUIRED)
        self.assertIsNone(command.expected_fingerprint)
        self.assertIsNone(command.ttl)
        self.assertIsNone(command.replace_existing)
        self.assertIs(command.style, HighlightStyle.PROVIDER_DEFAULT)
        self.assertFalse(command.allow_scope_expansion)

    def test_accepted_does_not_imply_applied(self):
        _, command = self.command()
        result = HighlightResult(
            submission_status=SubmissionStatus.ACCEPTED,
            verification_status=VerificationStatus.UNVERIFIED,
            submitted_targets=command.targets,
            guard_mode_used=GuardMode.WEAK_IDENTITY_CHECK,
        )
        self.assertEqual((), result.verified_applied_targets)
        self.assertIsNone(result.expires_at)
        with self.assertRaises(ValueError):
            replace(result, verified_applied_targets=command.targets)
        with self.assertRaises(ValueError):
            replace(result, verification_status=VerificationStatus.VERIFIED_APPLIED)

    def test_rejected_and_indeterminate_do_not_invent_verification(self):
        _, command = self.command()
        for status in (SubmissionStatus.REJECTED, SubmissionStatus.INDETERMINATE):
            result = HighlightResult(submission_status=status,
                verification_status=VerificationStatus.UNVERIFIED,
                submitted_targets=command.targets,
                guard_mode_used=GuardMode.WEAK_IDENTITY_CHECK)
            self.assertEqual((), result.verified_applied_targets)

    async def test_missing_guard_rejected_before_effect(self):
        adapter, command = self.command()
        with self.assertRaisesRegex(OperationNotAllowedError, "strong guard unavailable"):
            await adapter.highlight(command)
        self.assertEqual((), adapter.highlight_history)

    async def test_explicit_weak_guard_does_not_require_fingerprint(self):
        adapter, command = self.command()
        result = await adapter.highlight(replace(command, guard_mode=GuardMode.WEAK_IDENTITY_CHECK))
        self.assertIs(result.guard_mode_used, GuardMode.WEAK_IDENTITY_CHECK)

    async def test_idempotency_returns_prior_result_and_rejects_changed_command(self):
        adapter, command = self.command()
        command = replace(command, expected_fingerprint=adapter.active_document.fingerprint)
        first = await adapter.highlight(command)
        self.assertEqual(first, await adapter.highlight(command))
        with self.assertRaises(OperationNotAllowedError):
            await adapter.highlight(replace(command, allow_scope_expansion=True))
        self.assertEqual((command,), adapter.highlight_history)

