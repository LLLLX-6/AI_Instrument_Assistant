from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_instrument_assistant.integrations.harness_hardware.secret_store import (
    HarnessHardwareSecretStore,
    SecretAlreadyExistsError,
    SecretNotFoundError,
)


class HarnessHardwareSecretStoreTests(unittest.TestCase):
    def test_missing_secret_is_never_created_implicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = HarnessHardwareSecretStore(Path(directory) / "secret.txt")
            with self.assertRaises(SecretNotFoundError):
                store.load()
            self.assertFalse(store.path.exists())

    def test_explicit_bootstrap_creates_exactly_256_bits_and_will_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = HarnessHardwareSecretStore(Path(directory) / "secret.txt")
            created = store.bootstrap()
            self.assertEqual(32, len(created))
            self.assertEqual(created, store.load())
            with self.assertRaises(SecretAlreadyExistsError):
                store.bootstrap()


if __name__ == "__main__":
    unittest.main()
