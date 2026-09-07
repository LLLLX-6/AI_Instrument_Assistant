from __future__ import annotations

import asyncio
import json
import threading
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from ai_instrument_assistant.bootstrap import build_fake_hardware_tool_composition
from ai_instrument_assistant.integrations.harness_hardware.dev_client import (
    AuthenticationRejectedError,
    HarnessHardwareDevClient,
)
from ai_instrument_assistant.integrations.harness_hardware.auth import compute_proof, new_nonce
from ai_instrument_assistant.integrations.harness_hardware.server import (
    BackendServerConfig,
    HarnessHardwareServer,
)


SECRET = bytes(range(32))
OPERATIONS = (
    ("hardware.get_status", {}),
    ("hardware.measure_frequency", {"channel": 1}),
    ("hardware.measure_vpp", {"channel": 1}),
    ("hardware.capture_waveform", {"channel": 1}),
    ("hardware.measure_pwm", {"channel": 1}),
)


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 7, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


async def begin_raw_handshake(socket: Any, secret: bytes = SECRET) -> tuple[dict[str, Any], dict[str, Any]]:
    client_instance_id = str(uuid4())
    client_nonce = new_nonce()
    hello = {
        "protocol": "aia-harness-hardware", "version": 1,
        "message_id": str(uuid4()), "type": "hello",
        "client_instance_id": client_instance_id, "client_nonce": client_nonce,
    }
    await socket.send(json.dumps(hello))
    challenge = json.loads(await socket.recv())
    proof = {
        "protocol": "aia-harness-hardware", "version": 1,
        "message_id": str(uuid4()), "type": "prove",
        "reply_to": challenge["message_id"],
        "challenge_id": challenge["challenge_id"],
        "proof": compute_proof(
            secret, client_instance_id=client_instance_id, client_nonce=client_nonce,
            server_nonce=challenge["server_nonce"], challenge_id=challenge["challenge_id"],
            expires_at=challenge["expires_at"],
        ),
    }
    return challenge, proof


def status_success() -> dict[str, Any]:
    return {
        "contract_version": "1.0", "ok": True,
        "operation": "hardware.get_status",
        "result": {
            "instrument": {
                "manufacturer": "AIA", "model": "Fake", "serial_number": "SIM",
                "firmware_version": "1",
            },
            "observed_at": "2026-09-06T12:00:00Z",
        },
    }


class CountingRuntime:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result or status_success()

    def execute(self, payload: Any) -> dict[str, Any]:
        self.calls.append(payload)
        return self.result


class BlockingRuntime(CountingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(self, payload: Any) -> dict[str, Any]:
        self.calls.append(payload)
        self.started.set()
        self.release.wait(2)
        return self.result


class HarnessHardwareServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.composition = build_fake_hardware_tool_composition()
        self.composition.connect()
        self.server = HarnessHardwareServer(
            runtime=self.composition.runtime,
            secret_loader=lambda: SECRET,
            config=BackendServerConfig(port=0, heartbeat_interval=0.05, heartbeat_timeout=0.2),
        )
        await self.server.start()

    async def asyncTearDown(self) -> None:
        await self.server.stop()
        self.composition.close()

    async def test_five_operations_exercise_actual_fake_hardware_runtime(self) -> None:
        client = HarnessHardwareDevClient(self.server.uri, SECRET)
        await client.connect_and_authenticate()
        try:
            for operation, arguments in OPERATIONS:
                with self.subTest(operation=operation):
                    response = await client.request(operation, arguments)
                    self.assertEqual("response", response["type"])
                    self.assertEqual(operation, response["operation"])
                    self.assertTrue(response["hardware_result"]["ok"])
                    encoded = json.dumps(response)
                    self.assertNotIn("time_values", encoded)
                    self.assertNotIn("voltage_values", encoded)
                    self.assertNotIn("USB0::", encoded)
        finally:
            await client.close()

    async def test_heartbeat_is_session_bound_and_does_not_call_runtime(self) -> None:
        runtime = CountingRuntime()
        server = await self._replacement_server(runtime)
        client = HarnessHardwareDevClient(server.uri, SECRET)
        await client.connect_and_authenticate()
        try:
            await client.ping()
            await asyncio.sleep(0.12)
            self.assertEqual([], runtime.calls)
            self.assertEqual(1, server.authenticated_session_count)
        finally:
            await client.close()

    async def test_wrong_proof_prove_before_challenge_and_pre_auth_request_reject(self) -> None:
        with self.subTest(case="wrong proof"):
            client = HarnessHardwareDevClient(self.server.uri, b"x" * 32)
            with self.assertRaises(AuthenticationRejectedError):
                await client.connect_and_authenticate()
            await client.close()

        for message_type, body in (
            ("prove", {"reply_to": str(uuid4()), "challenge_id": str(uuid4()), "proof": "A" * 43}),
            ("request", {"session_id": str(uuid4()), "operation": "hardware.get_status", "arguments": {}}),
        ):
            async with connect(self.server.uri, ping_interval=None) as socket:
                message = {
                    "protocol": "aia-harness-hardware", "version": 1,
                    "message_id": str(uuid4()), "type": message_type, **body,
                }
                await socket.send(json.dumps(message))
                response = json.loads(await socket.recv())
                self.assertEqual("rejected", response["type"])

    async def test_reconnect_has_new_session_and_old_or_foreign_session_is_rejected(self) -> None:
        first = HarnessHardwareDevClient(self.server.uri, SECRET)
        await first.connect_and_authenticate()
        old_session = first.session_id
        await first.close()
        second = HarnessHardwareDevClient(self.server.uri, SECRET)
        await second.connect_and_authenticate()
        try:
            self.assertNotEqual(old_session, second.session_id)
            response = await second.send_raw_request(
                "hardware.get_status", {}, session_id=old_session,
            )
            self.assertEqual("error", response["type"])
            self.assertEqual("session_invalid", response["code"])
        finally:
            await second.close()

    async def test_two_live_connections_cannot_share_a_session(self) -> None:
        first = HarnessHardwareDevClient(self.server.uri, SECRET)
        second = HarnessHardwareDevClient(self.server.uri, SECRET)
        await first.connect_and_authenticate()
        await second.connect_and_authenticate()
        try:
            response = await second.send_raw_request(
                "hardware.get_status", {}, session_id=first.session_id
            )
            self.assertEqual("session_invalid", response["code"])
            first_response = await first.request("hardware.get_status", {})
            self.assertEqual("response", first_response["type"])
        finally:
            await first.close()
            await second.close()

    async def test_expired_challenge_and_replayed_proof_are_rejected(self) -> None:
        clock = MutableClock()
        await self.server.stop()
        self.server = HarnessHardwareServer(
            runtime=CountingRuntime(), secret_loader=lambda: SECRET,
            config=BackendServerConfig(port=0, challenge_ttl=0.01), clock=clock,
        )
        await self.server.start()
        async with connect(self.server.uri, ping_interval=None) as socket:
            _, proof = await begin_raw_handshake(socket)
            clock.value += timedelta(seconds=1)
            await socket.send(json.dumps(proof))
            rejected = json.loads(await socket.recv())
            self.assertEqual("challenge_expired", rejected["code"])

        await self.server.stop()
        self.server = HarnessHardwareServer(
            runtime=CountingRuntime(), secret_loader=lambda: SECRET,
            config=BackendServerConfig(port=0),
        )
        await self.server.start()
        async with connect(self.server.uri, ping_interval=None) as socket:
            _, proof = await begin_raw_handshake(socket)
            await socket.send(json.dumps(proof))
            accepted = json.loads(await socket.recv())
            self.assertEqual("accepted", accepted["type"])
            await socket.send(json.dumps(proof))
            replay = json.loads(await socket.recv())
            self.assertEqual("replay_rejected", replay["code"])

    async def test_unanswered_server_heartbeat_expires_session_without_runtime_call(self) -> None:
        runtime = CountingRuntime()
        await self.server.stop()
        self.server = HarnessHardwareServer(
            runtime=runtime, secret_loader=lambda: SECRET,
            config=BackendServerConfig(
                port=0, heartbeat_interval=0.02, heartbeat_timeout=0.05
            ),
        )
        await self.server.start()
        async with connect(self.server.uri, ping_interval=None) as socket:
            _, proof = await begin_raw_handshake(socket)
            await socket.send(json.dumps(proof))
            accepted = json.loads(await socket.recv())
            self.assertEqual("accepted", accepted["type"])
            await asyncio.sleep(0.12)
            ping = json.loads(await socket.recv())
            self.assertEqual("ping", ping["type"])
            with self.assertRaises(ConnectionClosed):
                await socket.recv()
        self.assertEqual([], runtime.calls)

    async def _replacement_server(self, runtime: Any) -> HarnessHardwareServer:
        await self.server.stop()
        replacement = HarnessHardwareServer(
            runtime=runtime, secret_loader=lambda: SECRET,
            config=BackendServerConfig(port=0, heartbeat_interval=0.05, heartbeat_timeout=0.2),
        )
        await replacement.start()
        self.server = replacement
        return replacement


class HarnessHardwareRequestSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = CountingRuntime()
        self.server = HarnessHardwareServer(
            runtime=self.runtime, secret_loader=lambda: SECRET,
            config=BackendServerConfig(port=0, heartbeat_interval=1, heartbeat_timeout=2),
        )
        await self.server.start()
        self.client = HarnessHardwareDevClient(self.server.uri, SECRET)
        await self.client.connect_and_authenticate()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        await self.server.stop()

    async def test_malformed_and_unsupported_requests_have_zero_runtime_effects(self) -> None:
        malformed = await self.client.send_raw_request(
            "hardware.measure_pwm", {"channel": 3}
        )
        self.assertEqual("protocol_invalid", malformed["code"])
        unsupported = await self.client.send_raw_request("hardware.unknown", {})
        self.assertEqual("operation_not_allowed", unsupported["code"])
        self.assertEqual([], self.runtime.calls)

    async def test_hardware_ok_false_is_forwarded_as_normal_response(self) -> None:
        self.runtime.result = {
            "contract_version": "1.0", "ok": False,
            "operation": "hardware.get_status",
            "error": {"code": "hardware_unavailable", "message": "Unavailable", "details": {}},
        }
        response = await self.client.request("hardware.get_status", {})
        self.assertEqual("response", response["type"])
        self.assertFalse(response["hardware_result"]["ok"])

    async def test_invalid_backend_response_becomes_bounded_protocol_error(self) -> None:
        self.runtime.result = {"secret": "raw backend detail"}
        response = await self.client.request("hardware.get_status", {})
        self.assertEqual("error", response["type"])
        self.assertEqual("backend_response_invalid", response["code"])
        self.assertNotIn("raw backend", json.dumps(response))

    async def test_mismatched_canonical_error_operation_is_not_miscorrelated(self) -> None:
        self.runtime.result = {
            "contract_version": "1.0", "ok": False,
            "operation": "hardware.measure_vpp",
            "error": {"code": "hardware_unavailable", "message": "Unavailable", "details": {}},
        }
        response = await self.client.request("hardware.get_status", {})
        self.assertEqual("error", response["type"])
        self.assertEqual("backend_response_invalid", response["code"])

    async def test_oversized_frame_is_closed_before_runtime_dispatch(self) -> None:
        await self.client.close()
        async with connect(self.server.uri, ping_interval=None, max_size=70_000) as socket:
            await socket.send("x" * 65_537)
            with self.assertRaises(ConnectionClosed):
                await socket.recv()
        self.assertEqual([], self.runtime.calls)


class HarnessHardwareDuplicateAndDisconnectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.runtime = BlockingRuntime()
        self.server = HarnessHardwareServer(
            runtime=self.runtime, secret_loader=lambda: SECRET,
            config=BackendServerConfig(port=0, heartbeat_interval=1, heartbeat_timeout=2),
        )
        await self.server.start()
        self.client = HarnessHardwareDevClient(self.server.uri, SECRET)
        await self.client.connect_and_authenticate()

    async def asyncTearDown(self) -> None:
        self.runtime.release.set()
        await self.client.close()
        await self.server.stop()

    async def test_duplicate_in_flight_and_completed_never_reinvoke(self) -> None:
        request_id = str(uuid4())
        await self.client.send_request_frame("hardware.get_status", {}, message_id=request_id)
        self.assertTrue(await asyncio.to_thread(self.runtime.started.wait, 1))
        await self.client.send_request_frame("hardware.get_status", {}, message_id=request_id)
        duplicate = await self.client.receive()
        self.assertEqual("duplicate_message", duplicate["code"])
        self.runtime.release.set()
        response = await self.client.receive()
        self.assertEqual(request_id, response["reply_to"])
        await self.client.send_request_frame("hardware.get_status", {}, message_id=request_id)
        completed_duplicate = await self.client.receive()
        self.assertEqual("duplicate_message", completed_duplicate["code"])
        self.assertEqual(1, len(self.runtime.calls))

    async def test_disconnect_during_measurement_discards_late_result_and_never_replays(self) -> None:
        request_id = str(uuid4())
        await self.client.send_request_frame("hardware.get_status", {}, message_id=request_id)
        self.assertTrue(await asyncio.to_thread(self.runtime.started.wait, 1))
        old_session = self.client.session_id
        await self.client.close()

        replacement = HarnessHardwareDevClient(self.server.uri, SECRET)
        await replacement.connect_and_authenticate()
        try:
            self.assertNotEqual(old_session, replacement.session_id)
            self.runtime.release.set()
            await asyncio.sleep(0.1)
            await replacement.send_request_frame(
                "hardware.get_status", {}, message_id=request_id
            )
            duplicate = await replacement.receive()
            self.assertEqual("duplicate_message", duplicate["code"])
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(replacement.receive(), 0.05)
            self.assertEqual(1, len(self.runtime.calls))
            self.assertIn("late_result_discarded", {event.event for event in self.server.audit_events})
        finally:
            await replacement.close()


if __name__ == "__main__":
    unittest.main()
