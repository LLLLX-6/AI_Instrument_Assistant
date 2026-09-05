from __future__ import annotations
import unittest
import asyncio
import json
from pathlib import Path
from dataclasses import replace
from ai_instrument_assistant.application.ports.eda_interface import (
    HighlightCommand, GuardMode, SubmissionStatus, VerificationStatus,
)
from ai_instrument_assistant.integrations.jlceda.remote_adapter import JLCEDARemoteAdapter
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.errors import JLCEDAConnectionLostError, JLCEDARequestTimeoutError
from ai_instrument_assistant.integrations.jlceda.highlight_mapping import encode_ref
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4] / "protocols/jlceda/v1"
class Peer:
    def __init__(self, response):
        self.response = response
        self.calls = 0
    async def request(self, operation, payload, *, timeout):
        self.calls += 1
        if isinstance(self.response, Exception): raise self.response
        return self.response

class RemoteHighlightTests(unittest.IsolatedAsyncioTestCase):
    def setup_adapter(self, response):
        validator = SchemaValidator(SchemaRegistry.from_directory(ROOT))
        mapper = JLCEDADomainMapper()
        context = json.loads((ROOT / "fixtures/valid/eda-selection/wire-net-response.case.json").read_text())["instance"]["payload"]["context"]
        selection = mapper.map_selection_context(validator.validate_and_freeze(
            "aia://protocol/jlceda/v1/models/selection-context", context)).selection
        cmd = HighlightCommand(document_ref=selection.document_ref,
            expected_snapshot_id=selection.snapshot_id if hasattr(selection, "snapshot_id") else selection.document_ref.snapshot_id,
            targets=selection.selected_objects, idempotency_key="key",
            guard_mode=GuardMode.WEAK_IDENTITY_CHECK, allow_scope_expansion=True)
        peer = Peer(response)
        return JLCEDARemoteAdapter(request_client=peer, validator=validator, mapper=mapper), peer, cmd

    async def test_disconnect_preserves_indeterminate_and_does_not_replay(self):
        adapter, peer, cmd = self.setup_adapter(JLCEDAConnectionLostError("gone"))
        result = await adapter.highlight(cmd)
        self.assertIs(result.submission_status, SubmissionStatus.INDETERMINATE)
        self.assertIs(result.verification_status, VerificationStatus.UNVERIFIED)
        self.assertEqual((), result.verified_applied_targets)
        self.assertEqual(result, await adapter.highlight(cmd))
        self.assertEqual(1, peer.calls)

    async def test_strong_missing_guard_never_sends(self):
        adapter, peer, cmd = self.setup_adapter(None)
        with self.assertRaisesRegex(RuntimeError, "strong_guard_unavailable"):
            await adapter.highlight(replace(cmd, guard_mode=GuardMode.STRONG_REQUIRED))
        self.assertEqual(0, peer.calls)
    async def test_correlated_result_maps_unverified_and_duplicate_is_cached(self):
        for status in ("accepted", "rejected"):
            adapter, peer, cmd = self.setup_adapter(None)
            response = json.loads((ROOT / "fixtures/valid/highlight/response.case.json").read_text())["instance"]
            response["payload"]["result"]["submitted_targets"] = [encode_ref(v) for v in cmd.targets]
            response["payload"]["result"]["submission_status"] = status
            peer.response = response
            first, second = await asyncio.gather(adapter.highlight(cmd), adapter.highlight(cmd))
            self.assertEqual(first, second)
            self.assertEqual(status, first.submission_status.value)
            self.assertEqual(1, peer.calls)
            with self.assertRaisesRegex(RuntimeError, "idempotency_conflict"):
                await adapter.highlight(replace(cmd, allow_scope_expansion=False))
            self.assertEqual(1, peer.calls)

    async def test_timeout_and_malformed_result_are_uncertain_never_replayed(self):
        for response in (JLCEDARequestTimeoutError("late"), {"invalid": True}):
            adapter, peer, cmd = self.setup_adapter(response)
            result = await adapter.highlight(cmd)
            self.assertEqual(SubmissionStatus.INDETERMINATE, result.submission_status)
            self.assertEqual(result, await adapter.highlight(cmd))
            self.assertEqual(1, peer.calls)

    async def test_forged_visual_verification_is_not_trusted(self):
        adapter, peer, cmd = self.setup_adapter(None)
        response = json.loads((ROOT / "fixtures/valid/highlight/response.case.json").read_text())["instance"]
        result = response["payload"]["result"]
        result["submitted_targets"] = [encode_ref(v) for v in cmd.targets]
        result["verified_applied_targets"] = result["submitted_targets"]
        result["verification_status"] = "verified_applied"
        peer.response = response
        mapped = await adapter.highlight(cmd)
        self.assertEqual(SubmissionStatus.INDETERMINATE, mapped.submission_status)
        self.assertEqual((), mapped.verified_applied_targets)
