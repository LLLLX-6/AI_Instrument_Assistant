from __future__ import annotations

import base64
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from ai_instrument_assistant.integrations.jlceda.transport.auth import compute_proof
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import (
    ProtocolStateMachine,
)
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


UTC = timezone.utc
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
PROTOCOL_ROOT = REPOSITORY_ROOT / "protocols" / "jlceda" / "v1"
SECRET = bytes(range(32))
CONNECTION_ID = "connection-1"
CLIENT_ID = "33333333-3333-4333-8333-333333333333"
CLIENT_NONCE = base64.urlsafe_b64encode(b"A" * 32).decode().rstrip("=")


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 23, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class ProtocolStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()
        registry = SchemaRegistry.from_directory(PROTOCOL_ROOT)
        self.validator = SchemaValidator(registry)
        self.machine = ProtocolStateMachine(
            secret=SECRET,
            clock=self.clock,
            challenge_ttl=timedelta(seconds=10),
            heartbeat_interval=timedelta(seconds=5),
            heartbeat_timeout=timedelta(seconds=15),
        )
        self.machine.connect(CONNECTION_ID, "127.0.0.1")

    def test_non_localhost_connection_is_rejected(self) -> None:
        with self.assertRaises(PermissionError):
            self.machine.connect("remote", "192.0.2.10")

    def test_hmac_vector_matches_cross_language_contract(self) -> None:
        self.assertEqual(
            "9pCfy9emzR9AqdQnR3cHEdUyYjqG80juEQUDO7-YoPw",
            compute_proof(
                SECRET,
                client_instance_id=CLIENT_ID,
                challenge_id="55555555-5555-4555-8555-555555555555",
                client_nonce="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                server_nonce="BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
                expires_at="2026-08-23T08:00:11Z",
            ),
        )

    def test_valid_hmac_establishes_session_and_replay_is_rejected(self) -> None:
        challenge = self._start_handshake()
        proof = self._proof_for(challenge)
        accepted = self.machine.handle(CONNECTION_ID, self._validated(proof))

        self.assertEqual("accepted", accepted["phase"])
        self.assertTrue(self.machine.sessions.is_active(accepted["session_id"]))

        replay = self.machine.handle(CONNECTION_ID, self._validated(proof))
        self.assertEqual("rejected", replay["phase"])
        self.assertEqual("replay_detected", replay["reason_code"])

    def test_expired_challenge_is_rejected(self) -> None:
        challenge = self._start_handshake()
        self.clock.now += timedelta(seconds=11)
        rejected = self.machine.handle(
            CONNECTION_ID,
            self._validated(self._proof_for(challenge)),
        )
        self.assertEqual("challenge_expired", rejected["reason_code"])
        self.assertEqual(0, len(self.machine.sessions))

    def test_invalid_hmac_is_rejected_and_challenge_is_consumed(self) -> None:
        challenge = self._start_handshake()
        proof = self._proof_for(challenge)
        proof["proof"] = base64.urlsafe_b64encode(b"Z" * 32).decode().rstrip("=")
        rejected = self.machine.handle(CONNECTION_ID, self._validated(proof))
        self.assertEqual("authentication_failed", rejected["reason_code"])

        replay = self.machine.handle(
            CONNECTION_ID,
            self._validated(self._proof_for(challenge)),
        )
        self.assertEqual("replay_detected", replay["reason_code"])

    def test_heartbeat_correlates_and_refreshes_session(self) -> None:
        session_id = self._authenticate()
        self.clock.now += timedelta(seconds=5)
        ping = self._base("99999999-9999-4999-8999-999999999999") | {
            "session_id": session_id,
            "kind": "ping",
            "nonce": base64.urlsafe_b64encode(b"D" * 32).decode().rstrip("="),
        }
        pong = self.machine.handle(CONNECTION_ID, self._validated(ping))
        self.assertEqual("pong", pong["kind"])
        self.assertEqual(ping["message_id"], pong["reply_to_message_id"])
        self.assertEqual(ping["nonce"], pong["nonce"])
        self.assertEqual([], self.machine.heartbeat_timeouts())

    def test_heartbeat_timeout_and_disconnect_invalidate_session(self) -> None:
        session_id = self._authenticate()
        self.clock.now += timedelta(seconds=16)
        self.assertEqual([CONNECTION_ID], self.machine.heartbeat_timeouts())
        self.assertFalse(self.machine.sessions.is_active(session_id))

        replacement = self._authenticate()
        self.machine.disconnect(CONNECTION_ID)
        self.assertFalse(self.machine.sessions.is_active(replacement))

    def test_reconnect_uses_new_session_and_rejects_old_session_and_proof(self) -> None:
        first_challenge = self._start_handshake()
        first_proof = self._proof_for(first_challenge)
        first_accepted = self.machine.handle(
            CONNECTION_ID, self._validated(first_proof),
        )
        old_session = str(first_accepted["session_id"])

        self.machine.disconnect(CONNECTION_ID)
        self.assertFalse(self.machine.sessions.is_active(old_session))
        self.machine.connect(CONNECTION_ID, "127.0.0.1")

        old_ping = self._base("99999999-9999-4999-8999-999999999999") | {
            "session_id": old_session,
            "kind": "ping",
            "nonce": base64.urlsafe_b64encode(b"D" * 32).decode().rstrip("="),
        }
        with self.assertRaises(PermissionError):
            self.machine.handle(CONNECTION_ID, self._validated(old_ping))

        replay = self.machine.handle(CONNECTION_ID, self._validated(first_proof))
        self.assertEqual("replay_detected", replay["reason_code"])

        new_session = self._authenticate()
        self.assertNotEqual(old_session, new_session)
        self.assertTrue(self.machine.sessions.is_active(new_session))

    def _start_handshake(self) -> dict[str, object]:
        init = self._base("11111111-1111-4111-8111-111111111111") | {
            "kind": "hello",
            "phase": "init",
            "provider": "jlceda-pro",
            "client_instance_id": CLIENT_ID,
            "client_nonce": CLIENT_NONCE,
        }
        return self.machine.handle(CONNECTION_ID, self._validated(init))

    def _proof_for(self, challenge: dict[str, object]) -> dict[str, object]:
        proof = compute_proof(
            SECRET,
            client_instance_id=CLIENT_ID,
            challenge_id=str(challenge["challenge_id"]),
            client_nonce=CLIENT_NONCE,
            server_nonce=str(challenge["server_nonce"]),
            expires_at=str(challenge["expires_at"]),
        )
        return self._base("66666666-6666-4666-8666-666666666666") | {
            "kind": "hello",
            "phase": "prove",
            "reply_to_message_id": challenge["message_id"],
            "challenge_id": challenge["challenge_id"],
            "proof": proof,
        }

    def _authenticate(self) -> str:
        challenge = self._start_handshake()
        accepted = self.machine.handle(
            CONNECTION_ID,
            self._validated(self._proof_for(challenge)),
        )
        return str(accepted["session_id"])

    def _validated(self, message: dict[str, object]):
        return self.validator.validate_and_freeze(
            "aia://protocol/jlceda/v1/message", message,
        )

    def _base(self, message_id: str) -> dict[str, object]:
        return {
            "protocol": "aia-jlceda",
            "protocol_version": "1.0",
            "message_id": message_id,
            "sent_at": self.clock.now.isoformat().replace("+00:00", "Z"),
            "trace_id": "22222222-2222-4222-8222-222222222222",
        }


if __name__ == "__main__":
    unittest.main()
