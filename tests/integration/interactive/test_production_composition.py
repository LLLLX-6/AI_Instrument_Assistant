from __future__ import annotations

import base64
import asyncio
import hashlib
import hmac
import json
import socket
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from websockets.asyncio.client import connect

from ai_instrument_assistant.adapters.eda.in_memory import InMemoryEDAAdapter
from ai_instrument_assistant.application.interactive import (
    FrontendKind,
    InteractiveCapabilityUnavailableError,
    OperationBudget,
    SemanticOperation,
    WorkflowState,
)
from ai_instrument_assistant.application.services import design_selection_disambiguation
from ai_instrument_assistant.bootstrap.interactive import (
    compose_interactive_host,
    compose_jlceda_interactive_host,
)
from ai_instrument_assistant.integrations.interactive import (
    InteractiveEndpointConfig,
    ProductionDesignSelectionDecisionIssuer,
)
from tests.support.interactive_fakes import (
    synthetic_ambiguous_binding,
)


ROOT = Path(__file__).resolve().parents[3]


class CountingEDA(InMemoryEDAAdapter):
    def __init__(self) -> None:
        source = InMemoryEDAAdapter.for_pwm_out_scenario()
        super().__init__(source.active_document, source.selection_context)
        self.document_calls = 0
        self.selection_calls = 0
        self.block_selection = False
        self.selection_started = asyncio.Event()
        self.selection_release = asyncio.Event()

    async def get_active_document(self):
        self.document_calls += 1
        return await super().get_active_document()

    async def get_selection(self):
        self.selection_calls += 1
        self.selection_started.set()
        if self.block_selection:
            await self.selection_release.wait()
        return await super().get_selection()

    def use_selection_context(self, context) -> None:
        self._selection_context = context


class ProductionCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.secret = b"p" * 32
        self.temp = tempfile.TemporaryDirectory()
        secret_path = Path(self.temp.name) / "interactive-secret"
        secret_path.write_text(
            base64.urlsafe_b64encode(self.secret).rstrip(b"=").decode("ascii"),
            encoding="ascii",
        )
        self.secret_path = secret_path
        self.eda = CountingEDA()
        self.runtime = compose_interactive_host(
            repository_root=ROOT,
            eda=self.eda,
            design_selection_issuer=ProductionDesignSelectionDecisionIssuer(),
            interactive_config=InteractiveEndpointConfig(
                port=_free_port(),
                credential_reference=secret_path,
            ),
        )
        await self.runtime.start()

    async def asyncTearDown(self) -> None:
        await self.runtime.stop()
        self.temp.cleanup()

    async def test_real_production_factory_dispatches_observe_end_to_end(self) -> None:
        flow = self.runtime.host.start_workflow("observe PWM_OUT", "request-composition")
        flow = self.runtime.host.transition(
            flow.workflow_id,
            flow.revision,
            WorkflowState.OBSERVING_DESIGN,
        )
        async with connect(self.runtime.interactive_uri, ping_interval=None) as websocket:
            hello = await _authenticate_and_hello(websocket, self.secret)
            await websocket.recv()  # authoritative initial snapshot
            await websocket.send(json.dumps({
                "protocol": "aia-interactive/v1",
                "message_id": str(uuid4()),
                "sent_at": "2026-09-12T08:00:00Z",
                "message_type": "command",
                "application_generation": hello["application_generation"],
                "session_id": hello["session_id"],
                "correlation_id": "observe-command",
                "command": "design.observe",
                "payload": {
                    "workflow_id": str(flow.workflow_id),
                    "expected_workflow_revision": flow.revision,
                },
            }))
            snapshot = await _snapshot_with_state(websocket, "TARGET_RESOLVED")

        self.assertEqual(self.eda.document_calls, 1)
        self.assertEqual(self.eda.selection_calls, 1)
        self.assertEqual(snapshot["status"]["workflow_state"], "TARGET_RESOLVED")
        updated = self.runtime.host.get_workflow(flow.workflow_id)
        self.assertIsNotNone(updated.design_observation_ref)
        self.assertIsNotNone(updated.probe_target)
        self.assertEqual(self.runtime.host.execution_dispatch_count, 0)

    async def test_authoritative_status_snapshot_remains_available_during_provider_await(self) -> None:
        flow = self.runtime.host.start_workflow("observe PWM_OUT", "request-status-during-observe")
        flow = self.runtime.host.transition(
            flow.workflow_id,
            flow.revision,
            WorkflowState.OBSERVING_DESIGN,
        )
        self.eda.block_selection = True
        async with connect(self.runtime.interactive_uri, ping_interval=None) as websocket:
            hello = await _authenticate_and_hello(websocket, self.secret)
            await websocket.recv()
            await websocket.send(json.dumps(_command(hello, "design.observe", {
                "workflow_id": str(flow.workflow_id),
                "expected_workflow_revision": flow.revision,
            })))
            await asyncio.wait_for(self.eda.selection_started.wait(), 0.5)
            await websocket.send(json.dumps({
                "protocol": "aia-interactive-auth/v1",
                "phase": "snapshot_request",
            }))
            try:
                snapshot = await asyncio.wait_for(_any_snapshot(websocket), 0.5)
                self.assertEqual(snapshot["status"]["workflow_state"], "OBSERVING_DESIGN")
            finally:
                self.eda.selection_release.set()
            await _snapshot_with_state(websocket, "TARGET_RESOLVED")

        self.assertEqual(self.eda.selection_calls, 1)
        self.assertEqual(self.runtime.interactive_server.counters.snapshot_requests_received, 1)
        self.assertEqual(self.runtime.interactive_server.counters.snapshot_replies_sent, 1)

    async def test_full_factory_composes_real_jlceda_provider_boundary(self) -> None:
        provider_secret = Path(self.temp.name) / "provider-secret"
        provider_secret.write_text(
            base64.urlsafe_b64encode(b"j" * 32).rstrip(b"=").decode("ascii"),
            encoding="ascii",
        )
        composed = compose_jlceda_interactive_host(
            repository_root=ROOT,
            interactive_config=InteractiveEndpointConfig(
                port=_free_port(),
                credential_reference=self.secret_path,
            ),
            provider_credential_reference=provider_secret,
        )
        self.assertIsNotNone(composed.provider_gateway)
        self.assertEqual(composed.provider_port, 49624)
        self.assertEqual(composed.host.execution_dispatch_count, 0)

    async def test_challenge_answers_use_host_issuer_and_replay_fails_closed(self) -> None:
        flow = self.runtime.host.start_workflow("resolve target", "request-selection")
        flow = self.runtime.host.transition(flow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        context, _fixture_binding, _fixture_tokens = synthetic_ambiguous_binding()
        self.eda.use_selection_context(context)
        async with connect(self.runtime.interactive_uri, ping_interval=None) as websocket:
            hello = await _authenticate_and_hello(websocket, self.secret)
            await websocket.recv()
            await websocket.send(json.dumps(_command(hello, "design.observe", {
                "workflow_id": str(flow.workflow_id),
                "expected_workflow_revision": flow.revision,
            })))
            waiting = await _snapshot_with_state(websocket, "WAITING_FOR_DESIGN_SELECTION")
            stored = self.runtime.host.get_workflow(flow.workflow_id)
            self.assertEqual(stored.design_selection_context, context)
            self.assertIsNotNone(stored.design_selection_binding)
            self.assertIsNone(stored.probe_target)
            typed_binding = stored.design_selection_binding
            tokens = design_selection_disambiguation.candidate_choice_tokens(typed_binding)
            challenge = waiting["pending_challenges"][0]
            answer = _wire_challenge_answer(
                hello,
                challenge,
                {
                    "candidate_set_identity": typed_binding.candidate_set_fingerprint,
                    "candidate_identity": tokens[0][0],
                },
            )
            original = design_selection_disambiguation.issue_trusted_design_selection_decision
            with patch.object(
                design_selection_disambiguation,
                "issue_trusted_design_selection_decision",
                wraps=original,
            ) as delegated:
                await websocket.send(json.dumps(answer))
                await _snapshot_with_state(websocket, "TARGET_RESOLVED")
                self.assertEqual(delegated.call_count, 1)
                await websocket.send(json.dumps(answer))
                with self.assertRaises(Exception):
                    while True:
                        await websocket.recv()
                self.assertEqual(delegated.call_count, 1)
        self.assertEqual(self.runtime.host.execution_dispatch_count, 0)

    async def test_operation_and_physical_authority_are_deferred_but_cancel_remains_available(self) -> None:
        flow = self.runtime.host.start_workflow("authorize PWM", "request-authority")
        flow = self.runtime.host.transition(flow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        flow = self.runtime.host.transition(flow.workflow_id, 1, WorkflowState.DESIGN_CONTEXT_READY)
        flow = self.runtime.host.transition(flow.workflow_id, 2, WorkflowState.TARGET_RESOLVED)
        flow = self.runtime.host.prepare_measurement_plan(
            flow.workflow_id,
            flow.revision,
            "target:pwm-out",
            (SemanticOperation.MEASURE_PWM,),
            1,
            (OperationBudget(SemanticOperation.MEASURE_PWM, 1),),
        )
        with self.assertRaisesRegex(
            InteractiveCapabilityUnavailableError,
            "deferred to Harness",
        ):
            self.runtime.host.request_operation_authorization(
                flow.workflow_id, flow.revision, FrontendKind.JLCEDA, timedelta(minutes=1)
            )
        async with connect(self.runtime.interactive_uri, ping_interval=None) as websocket:
            hello = await _authenticate_and_hello(websocket, self.secret)
            await websocket.recv()
            cancel_flow = self.runtime.host.start_workflow("cancel", "request-cancel")
            await websocket.send(json.dumps(_command(hello, "workflow.cancel", {
                "workflow_id": str(cancel_flow.workflow_id),
                "expected_workflow_revision": cancel_flow.revision,
                "reason": "user_cancelled",
            })))
            await _snapshot_with_workflow_state(websocket, str(cancel_flow.workflow_id), "CANCELLED")
        self.assertEqual(self.runtime.host.execution_dispatch_count, 0)


async def _authenticate_and_hello(websocket, secret: bytes):
    challenge = json.loads(await websocket.recv())
    client_id = str(uuid4())
    client_nonce = "c" * 43
    canonical = "\n".join((
        "aia-interactive", "1.0", client_id, challenge["challenge_id"],
        client_nonce, challenge["server_nonce"], challenge["expires_at"],
    )).encode("utf-8")
    proof = base64.urlsafe_b64encode(
        hmac.new(secret, canonical, hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    await websocket.send(json.dumps({
        "protocol": "aia-interactive-auth/v1",
        "phase": "proof",
        "client_instance_id": client_id,
        "challenge_id": challenge["challenge_id"],
        "client_nonce": client_nonce,
        "proof": proof,
    }))
    accepted = json.loads(await websocket.recv())
    assert accepted["phase"] == "accepted"
    await websocket.send(json.dumps({
        "protocol": "aia-interactive/v1",
        "message_id": str(uuid4()),
        "sent_at": "2026-09-12T08:00:00Z",
        "message_type": "hello",
        "frontend_kind": "JLCEDA",
        "client_instance_id": client_id,
        "supported_versions": ["aia-interactive/v1"],
        "resume_cursor": None,
    }))
    return json.loads(await websocket.recv())


async def _snapshot_with_state(websocket, expected: str):
    for _ in range(20):
        message = json.loads(await websocket.recv())
        if message.get("event_type") != "workflow_snapshot":
            continue
        snapshot = message["payload"]["snapshot"]
        if snapshot["status"]["workflow_state"] == expected:
            return snapshot
    raise AssertionError(f"no snapshot reached {expected}")


async def _any_snapshot(websocket):
    while True:
        message = json.loads(await websocket.recv())
        if message.get("event_type") == "workflow_snapshot":
            return message["payload"]["snapshot"]


async def _snapshot_with_workflow_state(websocket, workflow_id: str, expected: str):
    for _ in range(20):
        message = json.loads(await websocket.recv())
        if message.get("event_type") != "workflow_snapshot":
            continue
        snapshot = message["payload"]["snapshot"]
        workflow = next((value for value in snapshot["workflows"] if value["workflow_id"] == workflow_id), None)
        if workflow is not None and workflow["state"] == expected:
            return snapshot
    raise AssertionError(f"workflow did not reach {expected}")


def _wire_challenge_answer(hello, challenge, answer):
    return {
        "protocol": "aia-interactive/v1",
        "message_id": str(uuid4()),
        "sent_at": "2026-09-12T08:00:00Z",
        "message_type": "challenge_answer",
        "application_generation": hello["application_generation"],
        "session_id": hello["session_id"],
        "workflow_id": challenge["workflow_id"],
        "expected_workflow_revision": challenge["workflow_revision"],
        "challenge_id": challenge["challenge_id"],
        "challenge_kind": challenge["challenge_kind"],
        "nonce": challenge["nonce"],
        "answer": answer,
    }


def _command(hello, command: str, payload: object):
    return {
        "protocol": "aia-interactive/v1",
        "message_id": str(uuid4()),
        "sent_at": "2026-09-12T08:00:00Z",
        "message_type": "command",
        "application_generation": hello["application_generation"],
        "session_id": hello["session_id"],
        "correlation_id": "command-correlation",
        "command": command,
        "payload": payload,
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as value:
        value.bind(("127.0.0.1", 0))
        return int(value.getsockname()[1])


if __name__ == "__main__":
    unittest.main()
