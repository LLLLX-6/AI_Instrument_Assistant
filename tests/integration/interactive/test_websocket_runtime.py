from __future__ import annotations

import base64
import hashlib
import hmac
import json
import socket
import unittest
import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from websockets.asyncio.client import connect

from ai_instrument_assistant.application.interactive import ApplicationHost
from ai_instrument_assistant.application.interactive.errors import FrontendConnectionError
from ai_instrument_assistant.integrations.interactive import (
    InteractiveEndpointConfig,
    InteractiveGateway,
    InteractiveHmacAuthenticator,
    InteractiveProtocolBinding,
    InteractiveWebSocketServer,
    InteractiveWireProjector,
)
from tests.support.interactive_fakes import FakeAuthenticator, FakeDecisionAuthorities


ROOT = Path(__file__).resolve().parents[3]


class ControllableActions:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.block = False
        self.fail = False

    async def request_design_observation(self, workflow_id, expected_revision):
        del workflow_id, expected_revision
        self.started.set()
        if self.block:
            await self.release.wait()
        if self.fail:
            raise RuntimeError("provider detail must remain bounded")

    async def prepare_measurement(self, workflow_id, expected_revision, payload):
        del workflow_id, expected_revision, payload

    async def highlight_target(self, workflow_id, expected_revision):
        del workflow_id, expected_revision

    async def request_teaching_publication(self, workflow_id, expected_revision):
        del workflow_id, expected_revision


class InteractiveWebSocketRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.secret = b"r" * 32
        authorities = FakeDecisionAuthorities()
        self.host = ApplicationHost(
            design_selection_issuer=authorities,
            operation_authorization_issuer=authorities,
            physical_confirmation_issuer=authorities,
        )
        protocol = InteractiveProtocolBinding.from_repository(ROOT)
        self.actions = ControllableActions()
        gateway = InteractiveGateway(
            host=self.host, protocol=protocol, authenticator=FakeAuthenticator(),
            actions=self.actions,
        )
        self.server = InteractiveWebSocketServer(
            config=InteractiveEndpointConfig(port=_free_port()), gateway=gateway,
            projector=InteractiveWireProjector(self.host, protocol),
            authenticator=InteractiveHmacAuthenticator(self.secret), heartbeat_interval=0.1,
        )
        await self.server.start()

    async def asyncTearDown(self) -> None:
        await self.server.stop()

    async def test_reconnect_creates_new_session_under_same_application_generation(self) -> None:
        first = await self._connect_once()
        second = await self._connect_once()
        self.assertEqual(first["application_generation"], second["application_generation"])
        self.assertNotEqual(first["session_id"], second["session_id"])
        self.assertNotEqual(first["connection_generation"], second["connection_generation"])
        self.assertEqual(self.server.counters.authenticated_connections, 2)

    async def test_wrong_frontend_kind_is_rejected(self) -> None:
        async with connect(self.server.uri, ping_interval=None) as websocket:
            await self._authenticate(websocket)
            await websocket.send(json.dumps(_hello("HARNESS")))
            with self.assertRaises(Exception):
                while True:
                    await websocket.recv()

    async def test_snapshot_request_is_served_while_async_command_is_pending(self) -> None:
        self.actions.block = True
        async with connect(self.server.uri, ping_interval=None) as websocket:
            hello = await self._authenticate_and_hello(websocket)
            await websocket.recv()
            await websocket.send(json.dumps(_command(hello)))
            await asyncio.wait_for(self.actions.started.wait(), 0.5)
            await websocket.send(json.dumps({
                "protocol": "aia-interactive-auth/v1", "phase": "snapshot_request"
            }))
            try:
                reply = await asyncio.wait_for(_next_snapshot(websocket), 0.5)
            finally:
                self.actions.release.set()
            self.assertEqual(reply["event_type"], "workflow_snapshot")
            self.assertEqual(self.server.counters.snapshot_requests_received, 1)
            self.assertEqual(self.server.counters.snapshot_replies_sent, 1)
            self.assertEqual(self.server.counters.command_dispatches, 1)

    async def test_bounded_command_failure_does_not_destroy_snapshot_session(self) -> None:
        self.actions.fail = True
        async with connect(self.server.uri, ping_interval=None) as websocket:
            hello = await self._authenticate_and_hello(websocket)
            await websocket.recv()
            await websocket.send(json.dumps(_command(hello)))
            await asyncio.wait_for(self.actions.started.wait(), 0.5)
            await websocket.send(json.dumps({
                "protocol": "aia-interactive-auth/v1", "phase": "snapshot_request"
            }))
            # The bounded command completion snapshot and the explicit Status
            # reply are distinct authoritative frames on the still-live session.
            await asyncio.wait_for(_next_snapshot(websocket), 0.5)
            reply = await asyncio.wait_for(_next_snapshot(websocket), 0.5)
            self.assertEqual(reply["event_type"], "workflow_snapshot")
            self.assertEqual(self.server.counters.command_failures, 1)
            self.assertEqual(self.server.counters.snapshot_replies_sent, 1)

    async def test_teardown_releases_connection_state_when_helper_task_already_failed(self) -> None:
        # Regression: a heartbeat or event-pump task can complete with
        # ConnectionClosed before teardown runs. Awaiting it after a no-op
        # cancel re-raises that exception; teardown must still reach the
        # authoritative gateway disconnect and drop local socket state.
        from websockets.exceptions import ConnectionClosedError
        from websockets.frames import Close

        websocket = await connect(self.server.uri, ping_interval=None)
        try:
            hello = await self._authenticate_and_hello(websocket)
            connection_id = UUID(str(hello["connection_id"]))
            tracked_socket = next(iter(self.server._connections))

            async def already_failed() -> None:
                raise ConnectionClosedError(Close(1006, "simulated"), None)

            failed_task = asyncio.create_task(already_failed())
            with self.assertRaises(ConnectionClosedError):
                await failed_task

            await self.server._teardown(
                tracked_socket, connection_id, (failed_task, None, None)
            )

            with self.assertRaises(FrontendConnectionError):
                self.host.get_connection(connection_id)
            self.assertNotIn(tracked_socket, self.server._connections)
            self.assertNotIn(tracked_socket, self.server._connection_ids)
        finally:
            await websocket.close()

    async def test_abrupt_client_disconnect_always_releases_host_connection(self) -> None:
        for _ in range(5):
            websocket = await connect(self.server.uri, ping_interval=None)
            hello = await self._authenticate_and_hello(websocket)
            await websocket.recv()
            connection_id = UUID(str(hello["connection_id"]))
            # Abrupt transport loss while heartbeat (0.1s) and event pump run.
            await asyncio.sleep(0.15)
            await websocket.close()
            for _ in range(50):
                try:
                    self.host.get_connection(connection_id)
                except FrontendConnectionError:
                    break
                await asyncio.sleep(0.02)
            else:
                self.fail("host connection state leaked after client disconnect")

    async def test_invalid_session_is_rejected_before_async_command_task(self) -> None:
        async with connect(self.server.uri, ping_interval=None) as websocket:
            hello = await self._authenticate_and_hello(websocket)
            await websocket.recv()
            command = _command(hello)
            command["session_id"] = str(uuid4())
            await websocket.send(json.dumps(command))
            with self.assertRaises(Exception):
                while True:
                    await websocket.recv()
        self.assertEqual(self.server.counters.command_dispatches, 0)

    async def _connect_once(self):
        async with connect(self.server.uri, ping_interval=None) as websocket:
            await self._authenticate(websocket)
            await websocket.send(json.dumps(_hello("JLCEDA")))
            acknowledgement = json.loads(await websocket.recv())
            snapshot = json.loads(await websocket.recv())
            self.assertEqual(acknowledgement["message_type"], "hello_ack")
            self.assertEqual(snapshot["event_type"], "workflow_snapshot")
            return acknowledgement

    async def _authenticate_and_hello(self, websocket):
        await self._authenticate(websocket)
        await websocket.send(json.dumps(_hello("JLCEDA")))
        acknowledgement = json.loads(await websocket.recv())
        self.assertEqual(acknowledgement["message_type"], "hello_ack")
        return acknowledgement

    async def _authenticate(self, websocket) -> None:
        challenge = json.loads(await websocket.recv())
        client_id = str(uuid4())
        client_nonce = "b" * 43
        canonical = "\n".join((
            "aia-interactive", "1.0", client_id, challenge["challenge_id"],
            client_nonce, challenge["server_nonce"], challenge["expires_at"],
        )).encode("utf-8")
        proof = base64.urlsafe_b64encode(
            hmac.new(self.secret, canonical, hashlib.sha256).digest()
        ).rstrip(b"=").decode("ascii")
        await websocket.send(json.dumps({
            "protocol": "aia-interactive-auth/v1", "phase": "proof",
            "client_instance_id": client_id, "challenge_id": challenge["challenge_id"],
            "client_nonce": client_nonce, "proof": proof,
        }))
        accepted = json.loads(await websocket.recv())
        self.assertEqual(accepted["phase"], "accepted")


def _hello(frontend: str) -> dict[str, object]:
    return {
        "protocol": "aia-interactive/v1", "message_id": str(uuid4()),
        "sent_at": "2026-09-12T08:00:00Z", "message_type": "hello",
        "frontend_kind": frontend, "client_instance_id": str(uuid4()),
        "supported_versions": ["aia-interactive/v1"], "resume_cursor": None,
    }


def _command(hello: dict[str, object]) -> dict[str, object]:
    return {
        "protocol": "aia-interactive/v1",
        "message_id": str(uuid4()),
        "sent_at": "2026-09-12T08:00:00Z",
        "message_type": "command",
        "application_generation": hello["application_generation"],
        "session_id": hello["session_id"],
        "correlation_id": "snapshot-coordination-test",
        "command": "design.observe",
        "payload": {
            "workflow_id": str(uuid4()),
            "expected_workflow_revision": 0,
        },
    }


async def _next_snapshot(websocket) -> dict[str, object]:
    while True:
        value = json.loads(await websocket.recv())
        if value.get("event_type") == "workflow_snapshot":
            return value


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as value:
        value.bind(("127.0.0.1", 0))
        return int(value.getsockname()[1])


if __name__ == "__main__":
    unittest.main()
