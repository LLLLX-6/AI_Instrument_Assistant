from __future__ import annotations

import base64
import hashlib
import hmac
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_instrument_assistant.integrations.interactive import (
    INTERACTIVE_AUTH_PROTOCOL,
    InteractiveEndpointConfig,
    InteractiveHmacAuthenticator,
    InteractiveReplayError,
)


class InteractiveEndpointConfigTests(unittest.TestCase):
    def test_default_is_separate_loopback_product_configuration(self) -> None:
        config = InteractiveEndpointConfig()
        self.assertEqual(config.bind_host, "127.0.0.1")
        self.assertEqual(config.port, 49626)
        self.assertEqual(config.protocol_version, "aia-interactive/v1")
        self.assertNotIn(config.port, {49624, 49625})

    def test_reserved_or_remote_endpoint_fails_closed(self) -> None:
        for values in ({"bind_host": "localhost"}, {"port": 49624}, {"port": 49625}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                InteractiveEndpointConfig(**values)

    def test_secret_is_loaded_by_reference_and_never_rendered(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "interactive.key"
            encoded = base64.urlsafe_b64encode(b"s" * 32).rstrip(b"=").decode("ascii")
            path.write_text(encoded, encoding="ascii")
            config = InteractiveEndpointConfig(credential_reference=path)
            self.assertEqual(config.load_credential(), b"s" * 32)
            self.assertNotIn(encoded, repr(config))


class InteractiveAuthenticationTests(unittest.TestCase):
    def test_exact_proof_is_accepted_once_and_replay_fails(self) -> None:
        secret = b"x" * 32
        auth = InteractiveHmacAuthenticator(secret)
        challenge = auth.issue_challenge()
        client_id = "11111111-1111-4111-8111-111111111111"
        client_nonce = "b" * 43
        canonical = "\n".join((
            "aia-interactive", "1.0", client_id, challenge.challenge_id,
            client_nonce, challenge.server_nonce, challenge.expires_at,
        )).encode("utf-8")
        proof = base64.urlsafe_b64encode(
            hmac.new(secret, canonical, hashlib.sha256).digest()
        ).rstrip(b"=").decode("ascii")
        self.assertEqual(auth.verify(challenge.challenge_id, client_id, client_nonce, proof), client_id)
        with self.assertRaises(InteractiveReplayError):
            auth.verify(challenge.challenge_id, client_id, client_nonce, proof)
        self.assertEqual(INTERACTIVE_AUTH_PROTOCOL, "aia-interactive-auth/v1")

    def test_wrong_proof_fails_without_consuming_reusable_authority(self) -> None:
        auth = InteractiveHmacAuthenticator(b"x" * 32)
        challenge = auth.issue_challenge()
        with self.assertRaises(PermissionError):
            auth.verify(
                challenge.challenge_id,
                "11111111-1111-4111-8111-111111111111",
                "b" * 43,
                "c" * 43,
            )
        with self.assertRaises(InteractiveReplayError):
            auth.verify(
                challenge.challenge_id,
                "11111111-1111-4111-8111-111111111111",
                "b" * 43,
                "c" * 43,
            )


if __name__ == "__main__":
    unittest.main()
