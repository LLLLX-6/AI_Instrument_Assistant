from __future__ import annotations

import asyncio
import base64
import json
import unittest
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from ai_instrument_assistant.integrations.jlceda.transport.auth import compute_proof
from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
PROTOCOL_ROOT = REPOSITORY_ROOT / "protocols" / "jlceda" / "v1"
SECRET = bytes(range(32))


class LocalWebSocketGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL_ROOT))
        machine = ProtocolStateMachine(
            secret=SECRET,
            heartbeat_interval=timedelta(seconds=1),
            heartbeat_timeout=timedelta(seconds=3),
        )
        self.gateway = LocalWebSocketGateway(
            validator=validator,
            state_machine=machine,
            handshake_timeout=2.0,
            heartbeat_poll_interval=0.05,
        )
        await self.gateway.start(port=0)

    async def asyncTearDown(self) -> None:
        await self.gateway.stop()

    async def test_accepts_connection_and_establishes_session(self) -> None:
        async with connect(self.gateway.uri) as socket:
            init = self._init()
            await socket.send(json.dumps(init))
            challenge = json.loads(await socket.recv())
            await socket.send(json.dumps(self._prove(init, challenge)))
            accepted = json.loads(await socket.recv())
            self.assertEqual("accepted", accepted["phase"])
            self.assertEqual(1, self.gateway.active_connection_count)

    async def test_malformed_message_is_rejected_before_state_machine(self) -> None:
        async with connect(self.gateway.uri) as socket:
            await socket.send(json.dumps({"kind": "hello", "phase": "init"}))
            with self.assertRaises(ConnectionClosed) as raised:
                await socket.recv()
            self.assertIsNotNone(raised.exception.rcvd)
            self.assertEqual(1008, raised.exception.rcvd.code)
        self.assertEqual(0, self.gateway.state_machine_dispatch_count)

    async def test_non_loopback_bind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LocalWebSocketGateway(
                validator=self.gateway.validator,
                state_machine=self.gateway.state_machine,
                host="0.0.0.0",
            )

    async def test_stop_cancels_connection_and_invalidates_session(self) -> None:
        socket = await connect(self.gateway.uri)
        init = self._init()
        await socket.send(json.dumps(init))
        challenge = json.loads(await socket.recv())
        await socket.send(json.dumps(self._prove(init, challenge)))
        accepted = json.loads(await socket.recv())
        session_id = accepted["session_id"]

        await self.gateway.stop()
        self.assertFalse(self.gateway.state_machine.sessions.is_active(session_id))
        await socket.close()

    async def test_peer_disconnect_immediately_invalidates_session(self) -> None:
        socket = await connect(self.gateway.uri)
        init = self._init()
        await socket.send(json.dumps(init))
        challenge = json.loads(await socket.recv())
        await socket.send(json.dumps(self._prove(init, challenge)))
        accepted = json.loads(await socket.recv())
        session_id = accepted["session_id"]
        self.assertTrue(self.gateway.state_machine.sessions.is_active(session_id))

        await socket.close()
        for _ in range(20):
            if not self.gateway.state_machine.sessions.is_active(session_id):
                break
            await asyncio.sleep(0)
        self.assertFalse(self.gateway.state_machine.sessions.is_active(session_id))

    async def test_backend_can_restart_on_the_same_configured_endpoint(self) -> None:
        configured_port = int(self.gateway.uri.rsplit(":", 1)[1])
        original_uri = self.gateway.uri
        await self.gateway.stop()

        await self.gateway.start(port=configured_port)

        self.assertEqual(original_uri, self.gateway.uri)
        async with connect(self.gateway.uri) as socket:
            init = self._init()
            await socket.send(json.dumps(init))
            challenge = json.loads(await socket.recv())
            await socket.send(json.dumps(self._prove(init, challenge)))
            accepted = json.loads(await socket.recv())
            self.assertEqual("accepted", accepted["phase"])

    def _init(self) -> dict[str, object]:
        return self._base() | {
            "kind": "hello",
            "phase": "init",
            "provider": "jlceda-pro",
            "client_instance_id": str(uuid4()),
            "client_nonce": base64.urlsafe_b64encode(b"A" * 32).decode().rstrip("="),
        }

    def _prove(
        self,
        init: dict[str, object],
        challenge: dict[str, object],
    ) -> dict[str, object]:
        return self._base(trace_id=str(init["trace_id"])) | {
            "kind": "hello",
            "phase": "prove",
            "reply_to_message_id": challenge["message_id"],
            "challenge_id": challenge["challenge_id"],
            "proof": compute_proof(
                SECRET,
                client_instance_id=str(init["client_instance_id"]),
                challenge_id=str(challenge["challenge_id"]),
                client_nonce=str(init["client_nonce"]),
                server_nonce=str(challenge["server_nonce"]),
                expires_at=str(challenge["expires_at"]),
            ),
        }

    def _base(self, trace_id: str | None = None) -> dict[str, object]:
        return {
            "protocol": "aia-jlceda",
            "protocol_version": "1.0",
            "message_id": str(uuid4()),
            "sent_at": "2026-08-23T08:00:00Z",
            "trace_id": trace_id or str(uuid4()),
        }


if __name__ == "__main__":
    unittest.main()
