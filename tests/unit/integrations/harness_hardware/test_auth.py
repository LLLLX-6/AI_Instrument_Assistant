from __future__ import annotations

import unittest

from ai_instrument_assistant.integrations.harness_hardware.auth import (
    canonical_proof_payload,
    compute_proof,
    verify_proof,
)


SECRET = bytes(range(32))


class HarnessHardwareAuthTests(unittest.TestCase):
    def test_hmac_is_deterministic_and_binds_every_handshake_field(self) -> None:
        fields = {
            "client_instance_id": "00000000-0000-4000-8000-000000000001",
            "client_nonce": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "server_nonce": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            "challenge_id": "00000000-0000-4000-8000-000000000002",
            "expires_at": "2026-09-06T12:00:30Z",
        }
        proof = compute_proof(SECRET, **fields)
        self.assertEqual("uj1x4_d46uIzSznKvTW5ud86AXAi19igKfXHR3ZSDp4", proof)
        self.assertEqual(43, len(proof))
        self.assertTrue(verify_proof(proof, compute_proof(SECRET, **fields)))
        for name in fields:
            changed = dict(fields)
            changed[name] += "x"
            with self.subTest(field=name):
                self.assertNotEqual(proof, compute_proof(SECRET, **changed))

    def test_payload_uses_harness_namespace_and_secret_must_be_256_bit(self) -> None:
        payload = canonical_proof_payload(
            client_instance_id="client", client_nonce="client-nonce",
            server_nonce="server-nonce", challenge_id="challenge",
            expires_at="expiry",
        )
        self.assertTrue(payload.startswith(b"aia-harness-hardware\n1\n"))
        with self.assertRaises(ValueError):
            compute_proof(
                b"short", client_instance_id="client", client_nonce="a",
                server_nonce="b", challenge_id="c", expires_at="d",
            )


if __name__ == "__main__":
    unittest.main()
