from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from ...application.interactive import InteractiveApplicationError
from .auth import INTERACTIVE_AUTH_PROTOCOL, InteractiveHmacAuthenticator
from .config import InteractiveEndpointConfig
from .gateway import InteractiveGateway
from .protocol import MAX_MESSAGE_BYTES
from .wire import InteractiveWireProjector


@dataclass(frozen=True, slots=True)
class InteractiveServerCounters:
    connections: int
    authenticated_connections: int
    protocol_messages: int
    initial_snapshots_sent: int
    snapshot_requests_received: int
    snapshot_replies_sent: int
    commands_received: int
    command_dispatches: int
    command_failures: int


class InteractiveWebSocketServer:
    """Application-Host-owned, loopback-only interactive listener."""

    def __init__(
        self,
        *,
        config: InteractiveEndpointConfig,
        gateway: InteractiveGateway,
        projector: InteractiveWireProjector,
        authenticator: InteractiveHmacAuthenticator | None = None,
        heartbeat_interval: float = 5.0,
    ) -> None:
        if heartbeat_interval <= 0:
            raise ValueError("heartbeat interval must be positive")
        self._config = config
        self._gateway = gateway
        self._projector = projector
        self._authenticator = authenticator or InteractiveHmacAuthenticator(config.load_credential())
        self._heartbeat_interval = heartbeat_interval
        self._server: Server | None = None
        self._connections: set[ServerConnection] = set()
        self._connection_ids: dict[ServerConnection, UUID] = {}
        self._connections_seen = 0
        self._authenticated_seen = 0
        self._messages_seen = 0
        self._initial_snapshots_sent = 0
        self._snapshot_requests_received = 0
        self._snapshot_replies_sent = 0
        self._commands_received = 0
        self._command_dispatches = 0
        self._command_failures = 0

    @property
    def uri(self) -> str:
        if self._server is None:
            raise RuntimeError("interactive listener is not running")
        sockets = self._server.sockets
        if not sockets:
            raise RuntimeError("interactive listener has no socket")
        return f"ws://{self._config.bind_host}:{int(sockets[0].getsockname()[1])}"

    @property
    def counters(self) -> InteractiveServerCounters:
        return InteractiveServerCounters(
            self._connections_seen,
            self._authenticated_seen,
            self._messages_seen,
            self._initial_snapshots_sent,
            self._snapshot_requests_received,
            self._snapshot_replies_sent,
            self._commands_received,
            self._command_dispatches,
            self._command_failures,
        )

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await serve(
            self._handle,
            self._config.bind_host,
            self._config.port,
            max_size=MAX_MESSAGE_BYTES,
            ping_interval=None,
            compression=None,
        )

    async def stop(self) -> None:
        connections = tuple(self._connections)
        for socket in connections:
            with suppress(ConnectionClosed):
                await socket.close(code=1000, reason="interactive Host stopping")
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()

    async def _handle(self, socket: ServerConnection) -> None:
        remote = socket.remote_address
        remote_host = str(remote[0]) if isinstance(remote, tuple) and remote else ""
        if remote_host not in {"127.0.0.1", "::1"}:
            await socket.close(code=4005, reason="local transport rejected")
            return
        self._connections.add(socket)
        self._connections_seen += 1
        connection_id: UUID | None = None
        heartbeat: asyncio.Task[None] | None = None
        events: asyncio.Task[None] | None = None
        command_task: asyncio.Task[None] | None = None
        send_lock = asyncio.Lock()
        try:
            challenge = self._authenticator.issue_challenge()
            await self._send(socket, challenge.to_wire())
            proof = await asyncio.wait_for(socket.recv(), 10.0)
            proof_value = _object(proof)
            if proof_value.get("protocol") != INTERACTIVE_AUTH_PROTOCOL or proof_value.get("phase") != "proof":
                await socket.close(code=4001, reason="authentication required")
                return
            principal = self._authenticator.verify(
                _text(proof_value, "challenge_id"), _text(proof_value, "client_instance_id"),
                _text(proof_value, "client_nonce"), _text(proof_value, "proof"),
            )
            await self._send(socket, {"protocol": INTERACTIVE_AUTH_PROTOCOL, "phase": "accepted"})
            hello = _object(await asyncio.wait_for(socket.recv(), 10.0))
            result = self._gateway.handle_authenticated_hello(hello, f"jlceda:{principal}")
            if result.connection.frontend_kind.value != "JLCEDA":
                await socket.close(code=4001, reason="frontend kind rejected")
                return
            connection_id = result.connection.connection_id
            self._connection_ids[socket] = connection_id
            self._authenticated_seen += 1
            await self._send(socket, result.acknowledgement, send_lock)
            await self._send(
                socket,
                self._projector.snapshot_event(result.connection, result.initial_subscription.snapshot),
                send_lock,
            )
            self._initial_snapshots_sent += 1
            heartbeat = asyncio.create_task(self._heartbeat(socket, send_lock), name="aia-interactive-heartbeat")
            events = asyncio.create_task(
                self._event_pump(socket, result.connection, result.initial_subscription.next_cursor, send_lock),
                name="aia-interactive-events",
            )
            async for raw in socket:
                if command_task is not None and command_task.done():
                    await command_task
                    command_task = None
                value = _object(raw)
                if value.get("protocol") == INTERACTIVE_AUTH_PROTOCOL:
                    phase = value.get("phase")
                    if phase == "pong":
                        continue
                    if phase == "snapshot_request":
                        self._snapshot_requests_received += 1
                        snapshot = self._gateway.current_snapshot(connection_id)
                        await self._send(
                            socket,
                            self._projector.snapshot_event(result.connection, snapshot),
                            send_lock,
                        )
                        self._snapshot_replies_sent += 1
                        continue
                    await socket.close(code=4003, reason="protocol control rejected")
                    return
                self._messages_seen += 1
                message_type = value.get("message_type")
                if message_type == "command":
                    self._gateway.validate_command_message(connection_id, value)
                    self._commands_received += 1
                    if command_task is not None and not command_task.done():
                        snapshot = self._gateway.current_snapshot(connection_id)
                        await self._send(
                            socket,
                            self._projector.snapshot_event(result.connection, snapshot),
                            send_lock,
                        )
                        continue
                    command_task = asyncio.create_task(
                        self._dispatch_command(
                            socket, send_lock, result.connection, connection_id, value
                        ),
                        name="aia-interactive-command",
                    )
                    continue
                elif message_type == "challenge_answer":
                    self._gateway.handle_challenge_answer(connection_id, value)
                else:
                    await socket.close(code=4003, reason="message type rejected")
                    return
                snapshot = self._gateway.current_snapshot(connection_id)
                await self._send(
                    socket, self._projector.snapshot_event(result.connection, snapshot), send_lock
                )
        except (
            InteractiveApplicationError,
            PermissionError,
            ValueError,
            TypeError,
            KeyError,
            TimeoutError,
        ):
            with suppress(ConnectionClosed):
                await socket.close(code=4003, reason="bounded interactive request rejected")
        except ConnectionClosed:
            pass
        finally:
            for task in (command_task, heartbeat, events):
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            if connection_id is not None:
                self._gateway.disconnect(connection_id)
            self._connection_ids.pop(socket, None)
            self._connections.discard(socket)

    async def _dispatch_command(
        self,
        socket: ServerConnection,
        send_lock: asyncio.Lock,
        connection: Any,
        connection_id: UUID,
        value: dict[str, Any],
    ) -> None:
        try:
            self._command_dispatches += 1
            await self._gateway.handle_command(connection_id, value)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._command_failures += 1
        try:
            snapshot = self._gateway.current_snapshot(connection_id)
            await self._send(socket, self._projector.snapshot_event(connection, snapshot), send_lock)
        except (ConnectionClosed, InteractiveApplicationError, PermissionError, ValueError, TypeError, KeyError):
            return

    async def _heartbeat(self, socket: ServerConnection, send_lock: asyncio.Lock) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            await self._send(
                socket, {"protocol": INTERACTIVE_AUTH_PROTOCOL, "phase": "heartbeat"}, send_lock
            )

    async def _event_pump(
        self, socket: ServerConnection, connection: Any, cursor: int, send_lock: asyncio.Lock
    ) -> None:
        current = cursor
        while True:
            await asyncio.sleep(0.1)
            batch = self._gateway.subscribe(connection.connection_id, current)
            for event in batch.events:
                await self._send(socket, self._projector.event(connection, event), send_lock)
            current = batch.next_cursor

    @staticmethod
    async def _send(
        socket: ServerConnection,
        value: Any,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("interactive frame exceeds bounded size")
        if send_lock is None:
            await socket.send(encoded)
            return
        async with send_lock:
            await socket.send(encoded)


def _object(raw: object) -> dict[str, Any]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("bounded text frame required")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("interactive object frame required")
    return value


def _text(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not 1 <= len(item) <= 256:
        raise ValueError("bounded authentication field required")
    return item
