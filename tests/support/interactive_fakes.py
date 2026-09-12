from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from ai_instrument_assistant.application.interactive import FrontendKind, TrustedDesignSelectionReceipt


class FakeTrustedDecisionIssuer:
    def __init__(self) -> None:
        self.design_calls = 0
        self.operation_calls = 0
        self.physical_calls = 0

    @property
    def total_calls(self) -> int:
        return self.design_calls + self.operation_calls + self.physical_calls

    def issue_design_selection(self, request):
        self.design_calls += 1
        return TrustedDesignSelectionReceipt(
            f"design-decision:{self.design_calls}",
            f"probe-target:{request.selected_candidate_identity}",
        )

    def issue_operation_authorization(self, request):
        self.operation_calls += 1
        return f"operation-scope:{self.operation_calls}"

    def issue_physical_confirmation(self, request):
        self.physical_calls += 1
        return f"physical-confirmation:{self.physical_calls}"


class FakeRuntimeHandle:
    def __init__(self, kind, log: list[str], ready: bool) -> None:
        self.kind = kind
        self.log = log
        self.ready = ready
        self.running = True
        self.crashed = False
        self.stop_calls = 0

    async def wait_ready(self) -> None:
        if not self.ready:
            await asyncio.Future()

    async def stop(self) -> None:
        if self.stop_calls:
            return
        self.stop_calls += 1
        self.log.append(f"stop:{self.kind.value}")
        self.running = False


class FakeManagedRuntime:
    def __init__(self, kind, log: list[str], ready: bool = True) -> None:
        self.kind = kind
        self.log = log
        self.ready = ready
        self.handle = None

    async def start(self):
        self.log.append(f"start:{self.kind.value}")
        self.handle = FakeRuntimeHandle(self.kind, self.log, self.ready)
        return self.handle

    def crash(self) -> None:
        assert self.handle is not None
        self.handle.crashed = True
        self.handle.running = False


class FakeContainment:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.attached: set[object] = set()

    def attach(self, handle) -> None:
        self.log.append(f"attach:{handle.kind.value}")
        self.attached.add(handle)

    def release(self, handle) -> None:
        self.log.append(f"release:{handle.kind.value}")
        self.attached.discard(handle)

    def close(self) -> None:
        self.log.append("containment:close")
        self.attached.clear()


class FakeSingleInstance:
    def __init__(self, result: str) -> None:
        self.result = result
        self.terminate_calls = 0
        self.release_calls = 0

    def acquire(self) -> str:
        return self.result

    def release(self) -> None:
        self.release_calls += 1

    def terminate_unknown(self) -> None:
        self.terminate_calls += 1


class FakeHostRunner:
    def __init__(self, fail_start: bool = False) -> None:
        self.starts = 0
        self.fail_start = fail_start

    async def start(self) -> None:
        self.starts += 1
        if self.fail_start:
            raise RuntimeError("synthetic startup failure")

    async def stop(self) -> None:
        return None


class FakeRuntimeLifecycle:
    def __init__(self) -> None:
        self.shutdown_calls = 0

    async def shutdown(self) -> None:
        self.shutdown_calls += 1


class FakeAuthenticator:
    def authenticate(self, frontend_kind, credential):
        expected = {
            FrontendKind.HARNESS: "harness-secret",
            FrontendKind.JLCEDA: "jlceda-secret",
        }
        return f"fake:{frontend_kind.value}" if expected.get(frontend_kind) == credential else None


class FakeFrontend:
    """Test-only frontend; it imports no Harness or JLCEDA SDK."""

    def __init__(self, gateway, kind, credential, versions=("aia-interactive/v1",)) -> None:
        self.gateway = gateway
        self.kind = kind
        self.credential = credential
        self.versions = versions
        self.handshake = None
        self.cursor = 0

    @property
    def connection(self):
        assert self.handshake is not None
        return self.handshake.connection

    def connect(self, resume_cursor=None):
        message = {
            "protocol": "aia-interactive/v1",
            "message_id": str(uuid4()),
            "sent_at": "2026-09-12T08:00:00Z",
            "message_type": "hello",
            "frontend_kind": self.kind.value,
            "client_instance_id": str(uuid4()),
            "supported_versions": list(self.versions),
            "resume_cursor": resume_cursor,
        }
        self.handshake = self.gateway.handle_hello(message, self.credential)
        self.cursor = self.handshake.initial_subscription.next_cursor
        return self.handshake

    def disconnect(self):
        self.gateway.disconnect(self.connection.connection_id)

    def subscribe(self, cursor=None):
        batch = self.gateway.subscribe(self.connection.connection_id, self.cursor if cursor is None else cursor)
        self.cursor = batch.next_cursor
        return batch

    def start_workflow(self, label, correlation):
        message = {
            "protocol": "aia-interactive/v1", "message_id": str(uuid4()),
            "sent_at": "2026-09-12T08:00:00Z", "message_type": "command",
            "application_generation": str(self.connection.application_generation),
            "session_id": str(self.connection.session_id), "correlation_id": correlation,
            "command": "workflow.start",
            "payload": {"safe_label": label, "harness_conversation_id": "conversation:fake"},
        }
        return self.gateway.handle_command(self.connection.connection_id, message)

    def cancel_message(self, workflow_id, revision):
        return {
            "protocol": "aia-interactive/v1", "message_id": str(uuid4()),
            "sent_at": "2026-09-12T08:00:00Z", "message_type": "command",
            "application_generation": str(self.connection.application_generation),
            "session_id": str(self.connection.session_id), "correlation_id": "cancel",
            "command": "workflow.cancel",
            "payload": {"workflow_id": str(workflow_id), "expected_workflow_revision": revision, "reason": "user_cancelled"},
        }
