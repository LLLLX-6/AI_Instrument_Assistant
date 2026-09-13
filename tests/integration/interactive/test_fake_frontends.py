from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    FrontendKind,
    WorkflowState,
)
from ai_instrument_assistant.integrations.interactive import (
    AuthenticationError,
    InteractiveGateway,
    InteractiveProtocolBinding,
    ProtocolNegotiationError,
)
from tests.support.interactive_fakes import FakeAuthenticator, FakeDecisionAuthorities, FakeFrontend


ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


class FakeFrontendIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        authorities = FakeDecisionAuthorities()
        self.host = ApplicationHost(
            design_selection_issuer=authorities,
            operation_authorization_issuer=authorities,
            physical_confirmation_issuer=authorities,
            clock=lambda: NOW,
        )
        self.gateway = InteractiveGateway(
            host=self.host,
            protocol=InteractiveProtocolBinding.from_repository(ROOT),
            authenticator=FakeAuthenticator(),
        )

    async def test_fake_harness_and_jlceda_connect_version_negotiate_and_receive_snapshot(self) -> None:
        harness = FakeFrontend(self.gateway, FrontendKind.HARNESS, "harness-secret")
        jlceda = FakeFrontend(self.gateway, FrontendKind.JLCEDA, "jlceda-secret")
        harness.connect()
        jlceda.connect()
        flow = await harness.start_workflow("inspect PWM_OUT", "request-1")
        batch = jlceda.subscribe(0)
        self.assertEqual(flow.state, WorkflowState.IDLE)
        self.assertTrue(any(item.workflow_id == flow.workflow_id for item in batch.snapshot.workflows))
        self.assertLessEqual(batch.snapshot.event_cursor, batch.next_cursor)

    async def test_wrong_version_and_credential_fail_without_application_authority(self) -> None:
        bad = FakeFrontend(self.gateway, FrontendKind.HARNESS, "wrong")
        with self.assertRaises(AuthenticationError):
            bad.connect()
        incompatible = FakeFrontend(
            self.gateway, FrontendKind.HARNESS, "harness-secret",
            versions=("aia-interactive/v99",),
        )
        with self.assertRaises(ProtocolNegotiationError):
            incompatible.connect()
        self.assertEqual(self.host.execution_dispatch_count, 0)

    async def test_fake_frontend_reconnect_gets_new_session_and_cannot_reuse_old_session_message(self) -> None:
        frontend = FakeFrontend(self.gateway, FrontendKind.HARNESS, "harness-secret")
        first = frontend.connect()
        flow = await frontend.start_workflow("inspect", "request-1")
        old_message = frontend.cancel_message(flow.workflow_id, flow.revision)
        frontend.disconnect()
        second = frontend.connect(resume_cursor=frontend.cursor)
        self.assertNotEqual(first.connection.session_id, second.connection.session_id)
        with self.assertRaises(AuthenticationError):
            await self.gateway.handle_command(second.connection.connection_id, old_message)

    async def test_session_message_with_wrong_application_generation_is_rejected(self) -> None:
        frontend = FakeFrontend(self.gateway, FrontendKind.HARNESS, "harness-secret")
        frontend.connect()
        flow = await frontend.start_workflow("inspect", "request-1")
        message = frontend.cancel_message(flow.workflow_id, flow.revision)
        message["application_generation"] = str(uuid4())
        with self.assertRaises(AuthenticationError):
            await self.gateway.handle_command(frontend.connection.connection_id, message)
        self.assertEqual(self.host.get_workflow(flow.workflow_id).state, WorkflowState.IDLE)
        self.assertEqual(self.host.execution_dispatch_count, 0)


if __name__ == "__main__":
    unittest.main()
