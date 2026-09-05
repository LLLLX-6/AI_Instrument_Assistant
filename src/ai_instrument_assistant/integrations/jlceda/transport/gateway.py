from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any
from uuid import uuid4

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from ai_instrument_assistant.protocol.schema_validator import (
    SchemaInstanceValidationError,
    SchemaValidator,
)

from .state_machine import MESSAGE_SCHEMA_REF, ProtocolStateMachine


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

                self.state_machine_dispatch_count += 1
                try:
                    response = self.state_machine.handle(connection_id, validated)
                except (ConnectionError, PermissionError, TypeError, KeyError):
                    await socket.close(code=1008, reason="protocol state rejected")
                    return
                if response:
                    self.validator.validate_and_freeze(MESSAGE_SCHEMA_REF, response)
                    await socket.send(json.dumps(response, separators=(",", ":")))
                    authenticated = response.get("phase") == "accepted" or authenticated
        except TimeoutError:
            await socket.close(code=1008, reason="handshake timeout")
        except ConnectionClosed:
            pass
        except asyncio.CancelledError:
            raise
        finally:
            self.state_machine.disconnect(connection_id)
            self._connections.pop(connection_id, None)

    async def _monitor_heartbeats(self) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_poll_interval)
            for connection_id in self.state_machine.heartbeat_timeouts():
                socket = self._connections.get(connection_id)
                if socket is not None:
                    await socket.close(code=1008, reason="heartbeat timeout")
