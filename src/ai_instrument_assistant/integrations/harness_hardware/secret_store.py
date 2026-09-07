from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path


DEFAULT_SECRET_PATH = Path(".aia-secrets") / "harness-hardware-psk.txt"


class SecretStoreError(RuntimeError):
    pass


class SecretNotFoundError(SecretStoreError):
    pass


class SecretAlreadyExistsError(SecretStoreError):
    pass


class SecretInvalidError(SecretStoreError):
    pass


class HarnessHardwareSecretStore:
    """Explicit local PSK bootstrap and bounded loading without path disclosure."""

    def __init__(self, path: Path = DEFAULT_SECRET_PATH) -> None:
        self.path = path

    def load(self) -> bytes:
        if not self.path.is_file():
            raise SecretNotFoundError("Harness Hardware secret is not initialized")
        try:
            encoded = self.path.read_text(encoding="ascii").strip()
            secret = base64.b64decode(
                encoded + "=", altchars=b"-_", validate=True
            )
        except (OSError, UnicodeError, ValueError) as error:
            raise SecretInvalidError("Harness Hardware secret is invalid") from error
        if len(encoded) != 43 or len(secret) != 32:
            raise SecretInvalidError("Harness Hardware secret is invalid")
        return secret

    def bootstrap(self) -> bytes:
        if self.path.exists():
            raise SecretAlreadyExistsError("Harness Hardware secret already exists")
        secret = secrets.token_bytes(32)
        encoded = base64.urlsafe_b64encode(secret).decode("ascii").rstrip("=")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="ascii", newline="\n") as stream:
                stream.write(encoded + "\n")
            os.chmod(self.path, 0o600)
        except FileExistsError as error:
            raise SecretAlreadyExistsError(
                "Harness Hardware secret already exists"
            ) from error
        return secret
