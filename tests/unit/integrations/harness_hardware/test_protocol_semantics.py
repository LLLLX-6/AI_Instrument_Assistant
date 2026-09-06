from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ai_instrument_assistant.integrations.harness_hardware.protocol_semantics import (
    CancellationState,
    DeliveryState,
    IndeterminateExecutionError,
    MessageSizeError,
    ProtocolContractState,
    ProtocolSemanticError,
)


class HarnessHardwareProtocolSemanticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = ProtocolContractState(connection_generation=1)
        self.session = str(uuid4())
        self.state.establish_session(self.session)

    def test_old_session_and_duplicate_message_ids_are_rejected(self) -> None:
        message_id = str(uuid4())
        self.state.observe_session_message(message_id, self.session)
        with self.assertRaises(ProtocolSemanticError):
            self.state.observe_session_message(message_id, self.session)
        with self.assertRaises(ProtocolSemanticError):
            self.state.observe_session_message(str(uuid4()), str(uuid4()))

    def test_response_correlation_and_unknown_reply_to(self) -> None:
        request_id = str(uuid4())
        self.state.mark_request_sent(request_id, "hardware.measure_pwm", self.session)
        self.state.receive_response(str(uuid4()), request_id, self.session)
        self.assertEqual(DeliveryState.RESPONSE_RECEIVED, self.state.request(request_id).delivery_state)
        with self.assertRaises(ProtocolSemanticError):
            self.state.receive_response(str(uuid4()), str(uuid4()), self.session)

    def test_duplicate_response_and_operation_mismatch_are_rejected(self) -> None:
        request_id = str(uuid4())
        self.state.mark_request_sent(request_id, "hardware.measure_frequency", self.session)
        with self.assertRaises(ProtocolSemanticError):
            self.state.receive_response(
                str(uuid4()), request_id, self.session,
                operation="hardware.measure_vpp",
            )
        self.state.receive_response(
            str(uuid4()), request_id, self.session,
            operation="hardware.measure_frequency",
        )
        with self.assertRaises(ProtocolSemanticError):
            self.state.receive_response(str(uuid4()), request_id, self.session)

    def test_replayed_challenge_or_proof_is_rejected(self) -> None:
        pre_auth = ProtocolContractState(connection_generation=2)
        challenge_id = str(uuid4())
        expires = datetime.now(timezone.utc) + timedelta(seconds=10)
        pre_auth.register_challenge(challenge_id, "server-nonce", expires)
        pre_auth.consume_proof(challenge_id, "proof-id")
        with self.assertRaises(ProtocolSemanticError):
            pre_auth.consume_proof(challenge_id, "proof-id-2")
        with self.assertRaises(ProtocolSemanticError):
            pre_auth.register_challenge(challenge_id, "another", expires)

    def test_sent_unconfirmed_disconnect_is_indeterminate_and_never_replayed(self) -> None:
        request_id = str(uuid4())
        self.state.mark_request_sent(request_id, "hardware.get_status", self.session)
        with self.assertRaises(IndeterminateExecutionError):
            self.state.disconnect()
        pending = self.state.request(request_id)
        self.assertEqual(DeliveryState.SENT_UNCONFIRMED, pending.delivery_state)
        self.assertFalse(pending.may_auto_replay)

    def test_client_cancellation_only_stops_waiting(self) -> None:
        request_id = str(uuid4())
        self.state.mark_request_sent(request_id, "hardware.capture_waveform", self.session)
        self.state.cancel_client_wait(request_id)
        pending = self.state.request(request_id)
        self.assertEqual(CancellationState.CLIENT_CANCELLED_WAIT, pending.cancellation_state)
        self.assertFalse(pending.measurement_cancelled)
        self.assertFalse(pending.may_auto_replay)
        disposition = self.state.receive_response(str(uuid4()), request_id, self.session)
        self.assertEqual("late_discarded", disposition)

    def test_connection_generation_prevents_old_response_reuse(self) -> None:
        request_id = str(uuid4())
        self.state.mark_request_sent(request_id, "hardware.measure_vpp", self.session)
        replacement = str(uuid4())
        self.state.establish_session(replacement, connection_generation=2)
        with self.assertRaises(ProtocolSemanticError):
            self.state.receive_response(str(uuid4()), request_id, self.session)

    def test_unknown_operation_and_oversized_message_are_rejected(self) -> None:
        with self.assertRaises(ProtocolSemanticError):
            self.state.mark_request_sent(str(uuid4()), "hardware.raw_scpi", self.session)
        with self.assertRaises(MessageSizeError):
            self.state.ensure_message_size(b"x" * 65_537)


if __name__ == "__main__":
    unittest.main()
