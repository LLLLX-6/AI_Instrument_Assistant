from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SECRET_PATH = REPOSITORY_ROOT / ".aia-secrets" / "jlceda-psk.txt"


def main() -> int:
    SECRET_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    value = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    try:
        descriptor = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"Secret already exists: {SECRET_PATH}")
        return 0
    with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
        stream.write(value + "\n")
    print(f"Generated a new 256-bit secret at: {SECRET_PATH}")
    print("The secret value was intentionally not printed. Do not commit or log it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
