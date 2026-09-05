from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from ai_instrument_assistant.protocol.schema_validator import (
    SchemaInstanceValidationError,
    SchemaValidator,
)

from ..errors import (
    JLCEDAConnectionLostError,
    JLCEDAProtocolError,
    JLCEDARequestTimeoutError,
    JLCEDATransportUnavailableError,
)

from .state_machine import MESSAGE_SCHEMA_REF, ProtocolStateMachine


@dataclass(slots=True)
class _PendingRequest:
    connection_id: str
    session_id: str
    operation: str
    trace_id: str
    future: asyncio.Future[dict[str, object]]


class LocalWebSocketGateway:
    """Loopback-only WebSocket transport; it contains no EDA business operations."""

    def __init__(
        self,
        *,
        validator: SchemaValidator,
        state_machine: ProtocolStateMachine,
        host: str = "127.0.0.1",
        handshake_timeout: float = 10.0,
        heartbeat_poll_interval: float = 1.0,
        max_message_bytes: int = 65_536,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("Gateway must bind exactly to 127.0.0.1")
        if handshake_timeout <= 0 or heartbeat_poll_interval <= 0:
            raise ValueError("Timeout intervals must be positive")
        self.validator = validator
        self.state_machine = state_machine
        self._host = host
        self._handshake_timeout = handshake_timeout
        self._heartbeat_poll_interval = heartbeat_poll_interval
        self._max_message_bytes = max_message_bytes
        self._server: Server | None = None
        self._connections: dict[str, ServerConnection] = {}
        self._authenticated_sessions: dict[str, str] = {}
        self._send_locks: dict[str, asyncio.Lock] = {}
        self._pending_requests: dict[str, _PendingRequest] = {}
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._port: int | None = None
        self.state_machine_dispatch_count = 0

    @property
    def uri(self) -> str:
        if self._port is None:
            raise RuntimeError("Gateway is not running")
        return f"ws://{self._host}:{self._port}"

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)

    @property
    def authenticated_session_count(self) -> int:
        return len(self._authenticated_sessions)

    async def request(
        self,
        operation: str,
        payload: object,
        *,
        timeout: float,
    ) -> object:
        """Send one validated request over the sole authenticated session."""
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        sessions = tuple(self._authenticated_sessions.items())
        if len(sessions) != 1:
            raise JLCEDATransportUnavailableError(
                "Exactly one authenticated JLCEDA session is required"
            )
        connection_id, session_id = sessions[0]
        try:
            self.state_machine.sessions.require(session_id, connection_id)
        except PermissionError as error:
            raise JLCEDATransportUnavailableError(
                "Authenticated JLCEDA session is no longer active"
            ) from error
        socket = self._connections.get(connection_id)
        if socket is None:
            raise JLCEDATransportUnavailableError(
                "Authenticated JLCEDA socket is unavailable"
            )
        message_id = str(uuid4())
        trace_id = str(uuid4())
        message: dict[str, object] = {
            "protocol": "aia-jlceda",
            "protocol_version": "1.0",
            "message_id": message_id,
            "sent_at": _timestamp(),
            "trace_id": trace_id,
            "session_id": session_id,
            "kind": "request",
            "operation": operation,
            "payload": payload,
        }
        try:
            self.validator.validate_and_freeze(MESSAGE_SCHEMA_REF, message)
        except SchemaInstanceValidationError as error:
            raise JLCEDAProtocolError(f"Outbound request rejected: {error}") from error

        future: asyncio.Future[dict[str, object]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_requests[message_id] = _PendingRequest(
            connection_id, session_id, operation, trace_id, future,
        )
        try:
            await self._send(connection_id, socket, message)
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout)
            except TimeoutError as error:
                raise JLCEDARequestTimeoutError(
                    f"JLCEDA operation timed out: {operation}"
                ) from error
        except ConnectionClosed as error:
            raise JLCEDAConnectionLostError(
                "JLCEDA connection closed while sending a request"
            ) from error
        finally:
            self._pending_requests.pop(message_id, None)
            if not future.done():
                future.cancel()

    async def start(self, *, port: int = 49624) -> None:
        if self._server is not None:
            raise RuntimeError("Gateway is already running")
        self._server = await serve(
            self._handle_connection,
            self._host,
            port,
            max_size=self._max_message_bytes,
            ping_interval=None,
            compression=None,
            open_timeout=self._handshake_timeout,
        )
        sockets = self._server.sockets
        if not sockets:
            raise RuntimeError("Gateway did not acquire a listening socket")
        self._port = int(sockets[0].getsockname()[1])
        self._heartbeat_task = asyncio.create_task(
            self._monitor_heartbeats(), name="aia-jlceda-heartbeat-monitor",
        )

    async def stop(self) -> None:
        task, self._heartbeat_task = self._heartbeat_task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        connections = tuple(self._connections.items())
        for connection_id, socket in connections:
            self._fail_pending(connection_id, "JLCEDA gateway stopped")
            self.state_machine.disconnect(connection_id)
            await socket.close(code=1001, reason="gateway stopping")

        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        self._port = None

    async def _handle_connection(self, socket: ServerConnection) -> None:
        connection_id = str(uuid4())
        remote = socket.remote_address
        remote_host = str(remote[0]) if isinstance(remote, tuple) and remote else ""
        try:
            self.state_machine.connect(connection_id, remote_host)
        except PermissionError:
            await socket.close(code=1008, reason="loopback connections only")
            return
        self._connections[connection_id] = socket
        self._send_locks[connection_id] = asyncio.Lock()
        authenticated = False
        try:
            while True:
                raw = await (
                    socket.recv()
                    if authenticated
                    else asyncio.wait_for(socket.recv(), self._handshake_timeout)
                )
                if not isinstance(raw, str):
                    await socket.close(code=1003, reason="text JSON messages only")
                    return
                try:
                    message: Any = json.loads(raw)
                except json.JSONDecodeError:
                    await socket.close(code=1007, reason="invalid JSON")
                    return
                try:
                    validated = self.validator.validate_and_freeze(
                        MESSAGE_SCHEMA_REF, message,
                    )
                except SchemaInstanceValidationError:
                    await socket.close(code=1008, reason="message schema rejected")
                    return

                if message.get("kind") == "response":
                    try:
                        self._accept_business_response(connection_id, message)
                    except (JLCEDAProtocolError, PermissionError):
                        await socket.close(code=1008, reason="response correlation rejected")
                        return
                    continue

                self.state_machine_dispatch_count += 1
                try:
                    response = self.state_machine.handle(connection_id, validated)
                except (ConnectionError, PermissionError, TypeError, KeyError):
                    await socket.close(code=1008, reason="protocol state rejected")
                    return
                if response:
                    self.validator.validate_and_freeze(MESSAGE_SCHEMA_REF, response)
                    await self._send(connection_id, socket, response)
                    authenticated = response.get("phase") == "accepted" or authenticated
                    if response.get("phase") == "accepted":
                        self._authenticated_sessions[connection_id] = str(
                            response["session_id"]
                        )
        except TimeoutError:
            await socket.close(code=1008, reason="handshake timeout")
        except ConnectionClosed:
            pass
        except asyncio.CancelledError:
            raise
        finally:
            self._fail_pending(connection_id, "JLCEDA connection was lost")
            self._authenticated_sessions.pop(connection_id, None)
            self.state_machine.disconnect(connection_id)
            self._connections.pop(connection_id, None)
            self._send_locks.pop(connection_id, None)

    async def _monitor_heartbeats(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_poll_interval)
            for connection_id in self.state_machine.heartbeat_timeouts():
                socket = self._connections.get(connection_id)
                if socket is not None:
                    await socket.close(code=1008, reason="heartbeat timeout")

    def _accept_business_response(
        self,
        connection_id: str,
        message: dict[str, object],
    ) -> None:
        session_id = str(message.get("session_id", ""))
        self.state_machine.sessions.require(session_id, connection_id)
        reply_to = str(message.get("reply_to_message_id", ""))
        pending = self._pending_requests.get(reply_to)
        if pending is None:
            raise JLCEDAProtocolError("Unknown or duplicate response correlation")
        if (
            pending.connection_id != connection_id
            or pending.session_id != session_id
            or pending.operation != message.get("operation")
            or pending.trace_id != message.get("trace_id")
        ):
            raise JLCEDAProtocolError("Response session or operation mismatch")
        self._pending_requests.pop(reply_to, None)
        if pending.future.done():
            raise JLCEDAProtocolError("Duplicate response")
        pending.future.set_result(message)

    async def _send(
        self,
        connection_id: str,
        socket: ServerConnection,
        message: dict[str, object],
    ) -> None:
        lock = self._send_locks.get(connection_id)
        if lock is None:
            raise JLCEDAConnectionLostError("JLCEDA send context is unavailable")
        serialized = json.dumps(message, separators=(",", ":"))
        async with lock:
            await socket.send(serialized)

    def _fail_pending(self, connection_id: str, detail: str) -> None:
        for message_id, pending in tuple(self._pending_requests.items()):
            if pending.connection_id != connection_id:
                continue
            self._pending_requests.pop(message_id, None)
            if not pending.future.done():
                pending.future.set_exception(JLCEDAConnectionLostError(detail))


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
