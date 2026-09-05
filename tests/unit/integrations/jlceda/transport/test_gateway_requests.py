from __future__ import annotations

import asyncio
import base64
import json
import unittest
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from ai_instrument_assistant.integrations.jlceda.errors import (
    JLCEDAConnectionLostError,
    JLCEDAProtocolError,
    JLCEDARequestTimeoutError,
    JLCEDATransportUnavailableError,
)
from ai_instrument_assistant.integrations.jlceda.transport.auth import compute_proof
from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


ROOT = Path(__file__).resolve().parents[5]
PROTOCOL_ROOT = ROOT / "protocols" / "jlceda" / "v1"
SECRET = bytes(range(32))


class GatewayBusinessRequestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL_ROOT))
        self.gateway = LocalWebSocketGateway(
            validator=validator,
            state_machine=ProtocolStateMachine(
                secret=SECRET,
                heartbeat_interval=timedelta(seconds=10),
                heartbeat_timeout=timedelta(seconds=30),
            ),
            heartbeat_poll_interval=1,
        )
        await self.gateway.start(port=0)

    async def asyncTearDown(self) -> None:
        await self.gateway.stop()

    async def test_request_requires_authenticated_session(self) -> None:
        with self.assertRaises(JLCEDATransportUnavailableError):
            await self.gateway.request(
                "eda.document.get_active", {}, timeout=0.1
            )

    async def test_correlated_response_completes_one_request(self) -> None:
        socket, session_id = await self._authenticated_socket()
        task = asyncio.create_task(
            self.gateway.request("eda.document.get_active", {}, timeout=1)
        )
        request = json.loads(await socket.recv())
        self.assertEqual(session_id, request["session_id"])
        await socket.send(json.dumps(_success_response(request)))

        response = await task

        self.assertEqual(request["message_id"], response["reply_to_message_id"])
        await socket.close()

    async def test_correlated_selection_response_completes_one_request(self) -> None:
        socket, session_id = await self._authenticated_socket()
        task = asyncio.create_task(
            self.gateway.request("eda.selection.get", {}, timeout=1)
        )
        request = json.loads(await socket.recv())
        self.assertEqual(session_id, request["session_id"])
        await socket.send(json.dumps(_selection_success_response(request)))

        response = await task

        self.assertEqual("eda.selection.get", response["operation"])
        self.assertEqual(request["message_id"], response["reply_to_message_id"])
        await socket.close()

    async def test_highlight_correlates_and_rejects_duplicate_response(self) -> None:
        socket, session_id = await self._authenticated_socket()
        fixture_root = PROTOCOL_ROOT / "fixtures/valid/highlight"
        command = json.loads((fixture_root / "request.case.json").read_text())["instance"]["payload"]
        task = asyncio.create_task(self.gateway.request("eda.view.highlight", command, timeout=1))
        request = json.loads(await socket.recv())
        response = json.loads((fixture_root / "response.case.json").read_text())["instance"]
        response.update(session_id=session_id, reply_to_message_id=request["message_id"], trace_id=request["trace_id"])
        await socket.send(json.dumps(response))
        self.assertEqual(response, await task)
        await socket.send(json.dumps(response))
        with self.assertRaises(ConnectionClosed):
            await socket.recv()

    async def test_highlight_disconnect_after_delivery_preserves_lost_connection(self) -> None:
        socket, _ = await self._authenticated_socket()
        command = json.loads((PROTOCOL_ROOT / "fixtures/valid/highlight/request.case.json").read_text())["instance"]["payload"]
        task = asyncio.create_task(self.gateway.request("eda.view.highlight", command, timeout=1))
        await socket.recv()
        await socket.close()
        with self.assertRaises(JLCEDAConnectionLostError):
            await task

    async def test_timeout_removes_pending_request(self) -> None:
        socket, _ = await self._authenticated_socket()
        task = asyncio.create_task(
            self.gateway.request("eda.document.get_active", {}, timeout=0.01)
        )
        await socket.recv()
        with self.assertRaises(JLCEDARequestTimeoutError):
            await task
        await socket.close()

    async def test_disconnect_fails_pending_request(self) -> None:
        socket, _ = await self._authenticated_socket()
        task = asyncio.create_task(
            self.gateway.request("eda.document.get_active", {}, timeout=1)
        )
        await socket.recv()
        await socket.close()
        with self.assertRaises(JLCEDAConnectionLostError):
            await task

    async def test_wrong_or_duplicate_correlation_is_rejected(self) -> None:
        socket, _ = await self._authenticated_socket()
        task = asyncio.create_task(
            self.gateway.request("eda.document.get_active", {}, timeout=1)
        )
        request = json.loads(await socket.recv())
        wrong = _success_response(request)
        wrong["reply_to_message_id"] = str(uuid4())
        await socket.send(json.dumps(wrong))
        with self.assertRaises((JLCEDAConnectionLostError, JLCEDARequestTimeoutError)):
            await task
        with self.assertRaises(ConnectionClosed):
            await socket.recv()

    async def test_duplicate_response_is_rejected_after_first_completion(self) -> None:
        socket, _ = await self._authenticated_socket()
        task = asyncio.create_task(
            self.gateway.request("eda.document.get_active", {}, timeout=1)
        )
        request = json.loads(await socket.recv())
        response = _success_response(request)
        await socket.send(json.dumps(response))
        await task
        await socket.send(json.dumps(response))
        with self.assertRaises(ConnectionClosed):
            await socket.recv()

    async def test_reconnect_cannot_deliver_response_for_old_session(self) -> None:
        old_socket, _ = await self._authenticated_socket()
        old_task = asyncio.create_task(
            self.gateway.request("eda.document.get_active", {}, timeout=1)
        )
        old_request = json.loads(await old_socket.recv())
        await old_socket.close()
        with self.assertRaises(JLCEDAConnectionLostError):
            await old_task

        new_socket, new_session = await self._authenticated_socket()
        self.assertNotEqual(old_request["session_id"], new_session)
        await new_socket.send(json.dumps(_success_response(old_request)))
        with self.assertRaises(ConnectionClosed):
            await new_socket.recv()

    async def test_unknown_outbound_operation_is_rejected_before_send(self) -> None:
        socket, _ = await self._authenticated_socket()
        with self.assertRaises(JLCEDAProtocolError):
            await self.gateway.request("eda.design.modify", {}, timeout=1)
        await socket.close()

    async def _authenticated_socket(self) -> tuple[ClientConnection, str]:
        socket = await connect(self.gateway.uri)
        init = _base() | {
            "kind": "hello",
            "phase": "init",
            "provider": "jlceda-pro",
            "client_instance_id": str(uuid4()),
            "client_nonce": base64.urlsafe_b64encode(b"A" * 32).decode().rstrip("="),
        }
        await socket.send(json.dumps(init))
        challenge = json.loads(await socket.recv())
        proof = _base(trace_id=init["trace_id"]) | {
            "kind": "hello",
            "phase": "prove",
            "reply_to_message_id": challenge["message_id"],
            "challenge_id": challenge["challenge_id"],
            "proof": compute_proof(
                SECRET,
                client_instance_id=init["client_instance_id"],
                challenge_id=challenge["challenge_id"],
                client_nonce=init["client_nonce"],
                server_nonce=challenge["server_nonce"],
                expires_at=challenge["expires_at"],
            ),
        }
        await socket.send(json.dumps(proof))
        accepted = json.loads(await socket.recv())
        return socket, accepted["session_id"]


def _base(trace_id: str | None = None) -> dict[str, str]:
    return {
        "protocol": "aia-jlceda",
        "protocol_version": "1.0",
        "message_id": str(uuid4()),
        "sent_at": "2026-09-05T08:00:00Z",
        "trace_id": trace_id or str(uuid4()),
    }


def _success_response(request: dict[str, Any]) -> dict[str, Any]:
    return _base(trace_id=request["trace_id"]) | {
        "session_id": request["session_id"],
        "kind": "response",
        "operation": "eda.document.get_active",
        "reply_to_message_id": request["message_id"],
        "status": "success",
        "payload": {
            "document": {
                "model_version": "1.0",
                "document_ref": {
                    "model_version": "1.0", "provider": "jlceda-pro",
                    "object_type": "document", "document_id": "official-document-uuid",
                    "snapshot_id": str(uuid4()), "native_id": "official-document-uuid",
                    "canonical_id": "jlceda-pro:document:official-document-uuid",
                    "display_name": None,
                },
                "project_id": None, "project_name": None, "document_name": None,
                "document_type": "schematic", "native_revision": None,
                "fingerprint": None, "is_dirty": None,
                "captured_at": "2026-09-05T08:00:00Z",
            }
        },
    }


def _selection_success_response(request: dict[str, Any]) -> dict[str, Any]:
    snapshot_id = str(uuid4())
    return _base(trace_id=request["trace_id"]) | {
        "session_id": request["session_id"],
        "kind": "response",
        "operation": "eda.selection.get",
        "reply_to_message_id": request["message_id"],
        "status": "success",
        "payload": {
            "context": {
                "model_version": "1.0",
                "selection": {
                    "model_version": "1.0",
                    "document_ref": {
                        "model_version": "1.0",
                        "provider": "jlceda-pro",
                        "object_type": "document",
                        "document_id": "document-1",
                        "snapshot_id": snapshot_id,
                        "native_id": "document-1",
                        "canonical_id": "jlceda-pro:document:document-1",
                        "display_name": None,
                    },
                    "selected_objects": [],
                    "primary_object": None,
                },
                "nets": [],
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
