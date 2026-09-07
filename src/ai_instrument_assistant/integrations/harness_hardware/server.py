from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from itertools import count
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from uuid import UUID, uuid4

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from ai_instrument_assistant.protocol.hardware import HardwareToolContractValidator
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import (
    SchemaInstanceValidationError,
    SchemaValidator,
)

from .auth import compute_proof, new_nonce, verify_proof
from .protocol_semantics import ALLOWED_OPERATIONS, MAX_MESSAGE_BYTES
from .runtime_port import HardwareResponseValidatorPort, HardwareRuntimePort


MESSAGE_SCHEMA_REF = (
    "https://aia.local/protocols/harness-hardware/v1/message.schema.json"
)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 49_625


class ConnectionState(StrEnum):
    CONNECTED_PREAUTH = "connected_preauth"
    CHALLENGE_ISSUED = "challenge_issued"
    AUTHENTICATED = "authenticated"
    CLOSING = "closing"
    CLOSED = "closed"


class AdapterErrorCode(StrEnum):
    PROTOCOL_INVALID = "protocol_invalid"
    AUTHENTICATION_FAILED = "authentication_failed"
    SESSION_INVALID = "session_invalid"
    MESSAGE_TOO_LARGE = "message_too_large"
    DUPLICATE_MESSAGE = "duplicate_message"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    BACKEND_RESPONSE_INVALID = "backend_response_invalid"
    ADAPTER_INTERNAL_ERROR = "adapter_internal_error"


@dataclass(frozen=True, slots=True)
class BackendServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    handshake_timeout: float = 10.0
    challenge_ttl: float = 10.0
    session_ttl: float = 3_600.0
    heartbeat_interval: float = 10.0
    heartbeat_timeout: float = 30.0
    max_message_bytes: int = MAX_MESSAGE_BYTES
    max_in_flight: int = 8
    max_request_history: int = 4_096

    def __post_init__(self) -> None:
        if self.host != DEFAULT_HOST:
            raise ValueError("Harness Hardware server must bind exactly to 127.0.0.1")
        if isinstance(self.port, bool) or not 0 <= self.port <= 65_535:
            raise ValueError("port must be between 0 and 65535")
        intervals = (
            self.handshake_timeout,
            self.challenge_ttl,
            self.session_ttl,
            self.heartbeat_interval,
            self.heartbeat_timeout,
        )
        if any(value <= 0 for value in intervals):
            raise ValueError("all timeout values must be positive")
        if self.heartbeat_timeout <= self.heartbeat_interval:
            raise ValueError("heartbeat_timeout must exceed heartbeat_interval")
        if self.max_message_bytes != MAX_MESSAGE_BYTES:
            raise ValueError("protocol v1 message limit is fixed at 65536 bytes")
        if not 1 <= self.max_in_flight <= 64:
            raise ValueError("max_in_flight must be between 1 and 64")
        if not 128 <= self.max_request_history <= 65_536:
            raise ValueError("max_request_history must be between 128 and 65536")


@dataclass(frozen=True, slots=True)
class BackendAuditEvent:
    generation: int
    event: str
    message_id: str | None = None
    operation: str | None = None
    outcome_class: str | None = None


@dataclass(slots=True)
class _ConnectionContext:
    connection_id: str
    generation: int
    socket: ServerConnection
    state: ConnectionState = ConnectionState.CONNECTED_PREAUTH
    client_instance_id: str | None = None
    client_nonce: str | None = None
    challenge_message_id: str | None = None
    challenge_id: str | None = None
    server_nonce: str | None = None
    challenge_expires_at: datetime | None = None
    challenge_consumed: bool = False
    session_id: str | None = None
    session_expires_at: datetime | None = None
    seen_message_ids: OrderedDict[str, None] = field(default_factory=OrderedDict)
    in_flight: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    heartbeat_message_id: str | None = None
    heartbeat_sent_at: float | None = None
    heartbeat_task: asyncio.Task[None] | None = None
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class HarnessHardwareServer:
    """Authenticated loopback WebSocket adapter for one HardwareRuntimePort."""

    def __init__(
        self,
        *,
        runtime: HardwareRuntimePort,
        secret_loader: Callable[[], bytes],
        config: BackendServerConfig = BackendServerConfig(),
        response_validator: HardwareResponseValidatorPort | None = None,
        message_validator: SchemaValidator | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        id_factory: Callable[[], UUID] = uuid4,
        nonce_factory: Callable[[], str] = new_nonce,
    ) -> None:
        self._runtime = runtime
        self._secret_loader = secret_loader
        self.config = config
        self._response_validator = response_validator or HardwareToolContractValidator()
        self._message_validator = message_validator or _build_message_validator()
        self._clock = clock
        self._id_factory = id_factory
        self._nonce_factory = nonce_factory
        self._secret: bytes | None = None
        self._server: Server | None = None
        self._port: int | None = None
        self._generation_counter = count(1)
        self._connections: dict[str, _ConnectionContext] = {}
        self._sessions: dict[str, str] = {}
        self._runtime_tasks: set[asyncio.Task[None]] = set()
        self._request_ledger: OrderedDict[str, str] = OrderedDict()
        self._audit_events: deque[BackendAuditEvent] = deque(maxlen=2_048)
        self._stopping = False

    @property
    def uri(self) -> str:
        if self._port is None:
            raise RuntimeError("Harness Hardware server is not running")
        return f"ws://{self.config.host}:{self._port}"

    @property
    def authenticated_session_count(self) -> int:
        return len(self._sessions)

    @property
    def audit_events(self) -> tuple[BackendAuditEvent, ...]:
        return tuple(self._audit_events)

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("Harness Hardware server is already running")
        secret = self._secret_loader()
        if not isinstance(secret, bytes) or len(secret) != 32:
            raise ValueError("Harness Hardware secret must contain exactly 256 bits")
        self._secret = secret
        self._stopping = False
        self._server = await serve(
            self._handle_connection,
            self.config.host,
            self.config.port,
            max_size=self.config.max_message_bytes,
            ping_interval=None,
            compression=None,
            open_timeout=self.config.handshake_timeout,
        )
        sockets = self._server.sockets
        if not sockets:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._secret = None
            raise RuntimeError("Harness Hardware server did not acquire a socket")
        self._port = int(sockets[0].getsockname()[1])

    async def stop(self) -> None:
        if self._server is None:
            return
        self._stopping = True
        contexts = tuple(self._connections.values())
        for context in contexts:
            context.state = ConnectionState.CLOSING
            if context.heartbeat_task is not None:
                context.heartbeat_task.cancel()
            with suppress(ConnectionClosed):
                await context.socket.close(code=1001, reason="backend stopping")

        server, self._server = self._server, None
        server.close()
        await server.wait_closed()
        if self._runtime_tasks:
            await asyncio.gather(*tuple(self._runtime_tasks), return_exceptions=True)
        self._connections.clear()
        self._sessions.clear()
        self._secret = None
        self._port = None
        self._stopping = False

    async def _handle_connection(self, socket: ServerConnection) -> None:
        remote = socket.remote_address
        remote_host = str(remote[0]) if isinstance(remote, tuple) and remote else ""
        if remote_host != DEFAULT_HOST:
            await socket.close(code=4003, reason="loopback required")
            return
        connection_id = str(self._id_factory())
        context = _ConnectionContext(
            connection_id=connection_id,
            generation=next(self._generation_counter),
            socket=socket,
        )
        self._connections[connection_id] = context
        self._audit(context, "connected")
        try:
            while context.state not in {ConnectionState.CLOSING, ConnectionState.CLOSED}:
                raw = await (
                    socket.recv()
                    if context.state is ConnectionState.AUTHENTICATED
                    else asyncio.wait_for(socket.recv(), self.config.handshake_timeout)
                )
                if not isinstance(raw, str):
                    await socket.close(code=4003, reason="text JSON required")
                    return
                if len(raw.encode("utf-8")) > self.config.max_message_bytes:
                    self._audit(context, "message_too_large", outcome="rejected")
                    await socket.close(code=1009, reason="message too large")
                    return
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await socket.close(code=4003, reason="invalid JSON")
                    return
                if not isinstance(message, dict):
                    await socket.close(code=4003, reason="invalid message")
                    return
                try:
                    self._message_validator.validate_and_freeze(
                        MESSAGE_SCHEMA_REF, message
                    )
                except SchemaInstanceValidationError:
                    await self._handle_schema_rejection(context, message)
                    continue
                keep_open = await self._handle_valid_message(context, message)
                if not keep_open:
                    return
        except TimeoutError:
            with suppress(ConnectionClosed):
                await socket.close(code=4001, reason="authentication timeout")
        except ConnectionClosed as error:
            close_code = (
                error.rcvd.code
                if error.rcvd is not None
                else error.sent.code if error.sent is not None else None
            )
            if close_code == 1009:
                self._audit(context, "message_too_large", outcome="rejected")
        except asyncio.CancelledError:
            raise
        except Exception:
            self._audit(context, "adapter_internal_error", outcome="bounded")
            with suppress(ConnectionClosed):
                await socket.close(code=4005, reason="adapter failure")
        finally:
            await self._close_context(context)

    async def _handle_schema_rejection(
        self,
        context: _ConnectionContext,
        message: dict[str, Any],
    ) -> None:
        message_id = message.get("message_id")
        if context.state is not ConnectionState.AUTHENTICATED or not _is_uuid(message_id):
            await context.socket.close(code=4003, reason="message schema rejected")
            context.state = ConnectionState.CLOSING
            return
        operation = message.get("operation")
        code = (
            AdapterErrorCode.OPERATION_NOT_ALLOWED
            if message.get("type") == "request"
            and isinstance(operation, str)
            and operation not in ALLOWED_OPERATIONS
            else AdapterErrorCode.PROTOCOL_INVALID
        )
        await self._send_error(context, str(message_id), code)

    async def _handle_valid_message(
        self,
        context: _ConnectionContext,
        message: dict[str, Any],
    ) -> bool:
        message_type = message["type"]
        if context.state is ConnectionState.CONNECTED_PREAUTH:
            if message_type != "hello":
                await self._send_rejected(
                    context, message["message_id"], "authentication_failed"
                )
                return False
            await self._accept_hello(context, message)
            return True
        if context.state is ConnectionState.CHALLENGE_ISSUED:
            if message_type != "prove":
                await self._send_rejected(
                    context, message["message_id"], "authentication_failed"
                )
                return False
            return await self._accept_proof(context, message)
        if context.state is not ConnectionState.AUTHENTICATED:
            return False

        if message_type in {"hello", "challenge", "prove", "accepted", "rejected"}:
            await self._send_rejected(context, message["message_id"], "replay_rejected")
            return False
        if not self._session_matches(context, message.get("session_id")):
            await self._send_error(
                context, message["message_id"], AdapterErrorCode.SESSION_INVALID
            )
            return False
        if message["message_id"] in context.seen_message_ids:
            await self._send_error(
                context, message["message_id"], AdapterErrorCode.DUPLICATE_MESSAGE
            )
            return True
        self._remember_message_id(context, message["message_id"])

        if message_type == "request":
            await self._schedule_request(context, message)
        elif message_type == "ping":
            await self._send(
                context,
                {
                    **self._session_envelope(context, "pong"),
                    "reply_to": message["message_id"],
                    "sent_at": _timestamp(self._now()),
                },
            )
        elif message_type == "pong":
            if message["reply_to"] != context.heartbeat_message_id:
                await self._send_error(
                    context, message["message_id"], AdapterErrorCode.PROTOCOL_INVALID
                )
            else:
                context.heartbeat_message_id = None
                context.heartbeat_sent_at = None
        else:
            await self._send_error(
                context, message["message_id"], AdapterErrorCode.PROTOCOL_INVALID
            )
        return True

    async def _accept_hello(
        self,
        context: _ConnectionContext,
        message: dict[str, Any],
    ) -> None:
        self._remember_message_id(context, message["message_id"])
        context.client_instance_id = message["client_instance_id"]
        context.client_nonce = message["client_nonce"]
        context.challenge_message_id = str(self._id_factory())
        context.challenge_id = str(self._id_factory())
        context.server_nonce = self._nonce_factory()
        context.challenge_expires_at = self._now() + timedelta(
            seconds=self.config.challenge_ttl
        )
        context.state = ConnectionState.CHALLENGE_ISSUED
        await self._send(
            context,
            {
                "protocol": "aia-harness-hardware",
                "version": 1,
                "message_id": context.challenge_message_id,
                "type": "challenge",
                "reply_to": message["message_id"],
                "challenge_id": context.challenge_id,
                "client_nonce": context.client_nonce,
                "server_nonce": context.server_nonce,
                "algorithm": "hmac-sha256",
                "expires_at": _timestamp(context.challenge_expires_at),
            },
        )

    async def _accept_proof(
        self,
        context: _ConnectionContext,
        message: dict[str, Any],
    ) -> bool:
        if context.challenge_consumed:
            await self._send_rejected(context, message["message_id"], "replay_rejected")
            return False
        context.challenge_consumed = True
        if (
            message["reply_to"] != context.challenge_message_id
            or message["challenge_id"] != context.challenge_id
        ):
            await self._send_rejected(
                context, message["message_id"], "authentication_failed"
            )
            return False
        assert context.challenge_expires_at is not None
        if self._now() > context.challenge_expires_at:
            await self._send_rejected(context, message["message_id"], "challenge_expired")
            return False
        assert self._secret is not None
        expected = compute_proof(
            self._secret,
            client_instance_id=str(context.client_instance_id),
            client_nonce=str(context.client_nonce),
            server_nonce=str(context.server_nonce),
            challenge_id=str(context.challenge_id),
            expires_at=_timestamp(context.challenge_expires_at),
        )
        if not verify_proof(message["proof"], expected):
            await self._send_rejected(
                context, message["message_id"], "authentication_failed"
            )
            return False

        self._remember_message_id(context, message["message_id"])
        context.session_id = str(self._id_factory())
        context.session_expires_at = self._now() + timedelta(
            seconds=self.config.session_ttl
        )
        context.state = ConnectionState.AUTHENTICATED
        self._sessions[context.session_id] = context.connection_id
        await self._send(
            context,
            {
                "protocol": "aia-harness-hardware",
                "version": 1,
                "message_id": str(self._id_factory()),
                "type": "accepted",
                "reply_to": message["message_id"],
                "session_id": context.session_id,
                "connection_generation": context.generation,
                "expires_at": _timestamp(context.session_expires_at),
            },
        )
        context.heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(context),
            name=f"aia-harness-heartbeat-{context.generation}",
        )
        self._audit(context, "authenticated")
        return True

    async def _schedule_request(
        self,
        context: _ConnectionContext,
        message: dict[str, Any],
    ) -> None:
        request_id = message["message_id"]
        if request_id in self._request_ledger:
            await self._send_error(
                context, request_id, AdapterErrorCode.DUPLICATE_MESSAGE
            )
            return
        if len(self._runtime_tasks) >= self.config.max_in_flight:
            await self._send_error(
                context, request_id, AdapterErrorCode.ADAPTER_INTERNAL_ERROR
            )
            return
        self._request_ledger[request_id] = "in_flight"
        task = asyncio.create_task(
            self._execute_request(context, message),
            name=f"aia-harness-request-{request_id}",
        )
        context.in_flight[request_id] = task
        self._runtime_tasks.add(task)
        task.add_done_callback(self._runtime_tasks.discard)

    async def _execute_request(
        self,
        context: _ConnectionContext,
        message: dict[str, Any],
    ) -> None:
        request_id = message["message_id"]
        operation = message["operation"]
        self._audit(context, "runtime_started", request_id, operation)
        try:
            canonical_request = {
                "contract_version": "1.0",
                "operation": operation,
                "arguments": message["arguments"],
            }
            result = await asyncio.to_thread(self._runtime.execute, canonical_request)
            try:
                self._response_validator.validate_runtime_response(result)
                if result.get("operation") != operation:
                    raise ValueError("backend response operation mismatch")
            except Exception:
                if self._is_current(context):
                    await self._send_error(
                        context, request_id, AdapterErrorCode.BACKEND_RESPONSE_INVALID
                    )
                self._audit(
                    context, "runtime_completed", request_id, operation,
                    outcome="backend_response_invalid",
                )
                return
            if not self._is_current(context):
                self._audit(
                    context, "late_result_discarded", request_id, operation,
                    outcome="connection_generation_inactive",
                )
                return
            await self._send(
                context,
                {
                    **self._session_envelope(context, "response"),
                    "reply_to": request_id,
                    "operation": operation,
                    "hardware_result": result,
                },
            )
            self._audit(
                context, "runtime_completed", request_id, operation,
                outcome="hardware_result",
            )
        except Exception:
            if self._is_current(context):
                with suppress(ConnectionClosed):
                    await self._send_error(
                        context, request_id, AdapterErrorCode.ADAPTER_INTERNAL_ERROR
                    )
            self._audit(
                context, "runtime_completed", request_id, operation,
                outcome="adapter_internal_error",
            )
        finally:
            context.in_flight.pop(request_id, None)
            self._request_ledger[request_id] = "completed"
            self._request_ledger.move_to_end(request_id)
            self._trim_request_ledger()

    async def _heartbeat_loop(self, context: _ConnectionContext) -> None:
        try:
            while self._is_current(context):
                await asyncio.sleep(self.config.heartbeat_interval)
                if not self._is_current(context):
                    return
                if context.heartbeat_message_id is not None:
                    assert context.heartbeat_sent_at is not None
                    if monotonic() - context.heartbeat_sent_at >= self.config.heartbeat_timeout:
                        context.state = ConnectionState.CLOSING
                        await context.socket.close(code=4002, reason="heartbeat timeout")
                        return
                    continue
                message_id = str(self._id_factory())
                context.heartbeat_message_id = message_id
                context.heartbeat_sent_at = monotonic()
                await self._send(
                    context,
                    {
                        **self._session_envelope(context, "ping", message_id=message_id),
                        "sent_at": _timestamp(self._now()),
                    },
                )
        except ConnectionClosed:
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            self._audit(context, "heartbeat_failed", outcome="bounded")
            if self._is_current(context):
                context.state = ConnectionState.CLOSING
                with suppress(ConnectionClosed):
                    await context.socket.close(code=4005, reason="heartbeat failure")

    async def _send_error(
        self,
        context: _ConnectionContext,
        reply_to: str,
        code: AdapterErrorCode,
    ) -> None:
        messages = {
            AdapterErrorCode.PROTOCOL_INVALID: "The protocol message is invalid.",
            AdapterErrorCode.AUTHENTICATION_FAILED: "Authentication failed.",
            AdapterErrorCode.SESSION_INVALID: "The session is invalid.",
            AdapterErrorCode.MESSAGE_TOO_LARGE: "The protocol message is too large.",
            AdapterErrorCode.DUPLICATE_MESSAGE: "The message identifier was already used.",
            AdapterErrorCode.OPERATION_NOT_ALLOWED: "The operation is not allowed.",
            AdapterErrorCode.BACKEND_RESPONSE_INVALID: "The backend response is invalid.",
            AdapterErrorCode.ADAPTER_INTERNAL_ERROR: "The backend adapter failed.",
        }
        await self._send(
            context,
            {
                **self._session_envelope(context, "error"),
                "reply_to": reply_to,
                "code": code.value,
                "message": messages[code],
            },
        )

    async def _send_rejected(
        self,
        context: _ConnectionContext,
        reply_to: str,
        code: str,
    ) -> None:
        await self._send(
            context,
            {
                "protocol": "aia-harness-hardware",
                "version": 1,
                "message_id": str(self._id_factory()),
                "type": "rejected",
                "reply_to": reply_to,
                "code": code,
                "message": "Authentication was rejected.",
            },
        )
        context.state = ConnectionState.CLOSING

    async def _send(
        self,
        context: _ConnectionContext,
        message: dict[str, Any],
    ) -> None:
        self._message_validator.validate_and_freeze(MESSAGE_SCHEMA_REF, message)
        serialized = json.dumps(message, separators=(",", ":"), ensure_ascii=True)
        if len(serialized.encode("utf-8")) > self.config.max_message_bytes:
            raise RuntimeError("outbound protocol message exceeds the fixed limit")
        async with context.send_lock:
            await context.socket.send(serialized)

    async def _close_context(self, context: _ConnectionContext) -> None:
        context.state = ConnectionState.CLOSED
        heartbeat, context.heartbeat_task = context.heartbeat_task, None
        if heartbeat is not None and heartbeat is not asyncio.current_task():
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
        if context.session_id is not None:
            self._sessions.pop(context.session_id, None)
        self._connections.pop(context.connection_id, None)
        self._audit(context, "disconnected")

    def _session_matches(self, context: _ConnectionContext, session_id: Any) -> bool:
        return (
            isinstance(session_id, str)
            and session_id == context.session_id
            and self._sessions.get(session_id) == context.connection_id
            and context.session_expires_at is not None
            and self._now() <= context.session_expires_at
            and self._connections.get(context.connection_id) is context
        )

    def _is_current(self, context: _ConnectionContext) -> bool:
        return (
            not self._stopping
            and context.state is ConnectionState.AUTHENTICATED
            and context.session_id is not None
            and self._sessions.get(context.session_id) == context.connection_id
            and self._connections.get(context.connection_id) is context
        )

    def _session_envelope(
        self,
        context: _ConnectionContext,
        message_type: str,
        *,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        assert context.session_id is not None
        return {
            "protocol": "aia-harness-hardware",
            "version": 1,
            "message_id": message_id or str(self._id_factory()),
            "session_id": context.session_id,
            "type": message_type,
        }

    def _audit(
        self,
        context: _ConnectionContext,
        event: str,
        message_id: str | None = None,
        operation: str | None = None,
        *,
        outcome: str | None = None,
    ) -> None:
        self._audit_events.append(
            BackendAuditEvent(
                generation=context.generation,
                event=event,
                message_id=message_id,
                operation=operation,
                outcome_class=outcome,
            )
        )

    def _trim_request_ledger(self) -> None:
        while len(self._request_ledger) > self.config.max_request_history:
            removable = next(
                (
                    request_id
                    for request_id, state in self._request_ledger.items()
                    if state == "completed"
                ),
                None,
            )
            if removable is None:
                return
            self._request_ledger.pop(removable, None)

    def _remember_message_id(
        self,
        context: _ConnectionContext,
        message_id: str,
    ) -> None:
        context.seen_message_ids[message_id] = None
        context.seen_message_ids.move_to_end(message_id)
        while len(context.seen_message_ids) > self.config.max_request_history:
            context.seen_message_ids.popitem(last=False)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)


def _build_message_validator() -> SchemaValidator:
    repository_root = Path(__file__).resolve().parents[4]
    protocol_root = repository_root / "protocols" / "harness-hardware" / "v1"
    hardware_schema = (
        repository_root / "protocols" / "hardware" / "v1" / "hardware-tool.schema.json"
    )
    paths = tuple(sorted(protocol_root.rglob("*.schema.json"))) + (hardware_schema,)
    return SchemaValidator(SchemaRegistry.from_files(paths))


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True
