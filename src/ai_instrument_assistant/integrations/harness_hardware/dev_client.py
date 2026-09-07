from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import ClientConnection, connect

from .auth import compute_proof, new_nonce
from .protocol_semantics import MAX_MESSAGE_BYTES


class AuthenticationRejectedError(PermissionError):
    pass


class HarnessHardwareDevClient:
    """Development/smoke client; it is not the future Harness plugin."""

    def __init__(self, uri: str, secret: bytes) -> None:
        if len(secret) != 32:
            raise ValueError("Harness Hardware PSK must contain exactly 256 bits")
        self.uri = uri
        self._secret = secret
        self._socket: ClientConnection | None = None
        self.client_instance_id = str(uuid4())
        self.session_id: str | None = None
        self.connection_generation: int | None = None

    async def connect_and_authenticate(self) -> None:
        if self._socket is not None:
            raise RuntimeError("client is already connected")
        self._socket = await connect(
            self.uri,
            ping_interval=None,
            compression=None,
            max_size=MAX_MESSAGE_BYTES,
        )
        client_nonce = new_nonce()
        hello_id = str(uuid4())
        await self._send(
            {
                "protocol": "aia-harness-hardware",
                "version": 1,
                "message_id": hello_id,
                "type": "hello",
                "client_instance_id": self.client_instance_id,
                "client_nonce": client_nonce,
            }
        )
        challenge = await self.receive()
        if challenge.get("type") != "challenge" or challenge.get("reply_to") != hello_id:
            raise AuthenticationRejectedError("Backend challenge was invalid")
        proof_id = str(uuid4())
        proof = compute_proof(
            self._secret,
            client_instance_id=self.client_instance_id,
            client_nonce=client_nonce,
            server_nonce=challenge["server_nonce"],
            challenge_id=challenge["challenge_id"],
            expires_at=challenge["expires_at"],
        )
        await self._send(
            {
                "protocol": "aia-harness-hardware",
                "version": 1,
                "message_id": proof_id,
                "type": "prove",
                "reply_to": challenge["message_id"],
                "challenge_id": challenge["challenge_id"],
                "proof": proof,
            }
        )
        accepted = await self.receive()
        if accepted.get("type") == "rejected":
            raise AuthenticationRejectedError("Backend rejected authentication")
        if accepted.get("type") != "accepted" or accepted.get("reply_to") != proof_id:
            raise AuthenticationRejectedError("Backend acceptance was invalid")
        self.session_id = accepted["session_id"]
        self.connection_generation = accepted["connection_generation"]

    async def request(
        self,
        operation: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        message_id = str(uuid4())
        await self.send_request_frame(operation, arguments, message_id=message_id)
        while True:
            response = await self.receive()
            if response.get("reply_to") == message_id:
                return response

    async def send_raw_request(
        self,
        operation: str,
        arguments: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        message_id = str(uuid4())
        await self.send_request_frame(
            operation,
            arguments,
            message_id=message_id,
            session_id=session_id,
        )
        while True:
            response = await self.receive()
            if response.get("reply_to") == message_id:
                return response

    async def send_request_frame(
        self,
        operation: str,
        arguments: dict[str, Any],
        *,
        message_id: str,
        session_id: str | None = None,
    ) -> None:
        active_session = session_id if session_id is not None else self.session_id
        if active_session is None:
            raise RuntimeError("client is not authenticated")
        await self._send(
            {
                "protocol": "aia-harness-hardware",
                "version": 1,
                "message_id": message_id,
                "session_id": active_session,
                "type": "request",
                "operation": operation,
                "arguments": arguments,
            }
        )

    async def ping(self) -> None:
        if self.session_id is None:
            raise RuntimeError("client is not authenticated")
        message_id = str(uuid4())
        await self._send(
            {
                "protocol": "aia-harness-hardware",
                "version": 1,
                "message_id": message_id,
                "session_id": self.session_id,
                "type": "ping",
                "sent_at": _timestamp(),
            }
        )
        while True:
            response = await self.receive()
            if response.get("type") == "pong" and response.get("reply_to") == message_id:
                return

    async def receive(self) -> dict[str, Any]:
        socket = self._require_socket()
        while True:
            raw = await socket.recv()
            if not isinstance(raw, str):
                raise ValueError("Backend returned a non-text message")
            message = json.loads(raw)
            if message.get("type") != "ping":
                return message
            if self.session_id is None:
                raise ValueError("Backend sent a session ping before authentication")
            await self._send(
                {
                    "protocol": "aia-harness-hardware",
                    "version": 1,
                    "message_id": str(uuid4()),
                    "session_id": self.session_id,
                    "type": "pong",
                    "reply_to": message["message_id"],
                    "sent_at": _timestamp(),
                }
            )

    async def close(self) -> None:
        socket, self._socket = self._socket, None
        self.session_id = None
        self.connection_generation = None
        if socket is not None:
            await socket.close(code=1000, reason="development client closed")

    async def _send(self, message: dict[str, Any]) -> None:
        serialized = json.dumps(message, separators=(",", ":"), ensure_ascii=True)
        if len(serialized.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("message exceeds the protocol limit")
        await self._require_socket().send(serialized)

    def _require_socket(self) -> ClientConnection:
        if self._socket is None:
            raise RuntimeError("client is not connected")
        return self._socket


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
