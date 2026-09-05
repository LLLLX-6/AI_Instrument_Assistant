from __future__ import annotations

import argparse
import asyncio
import base64
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


DEFAULT_SECRET_PATH = REPOSITORY_ROOT / ".aia-secrets" / "jlceda-psk.txt"
PROTOCOL_ROOT = REPOSITORY_ROOT / "protocols" / "jlceda" / "v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 5B.1 localhost gateway")
    parser.add_argument("--port", type=stable_port, default=49624)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    return parser.parse_args()


def stable_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("port must be an integer") from error
    if port < 1 or port > 65_535:
        raise argparse.ArgumentTypeError(
            "production gateway port must be stable and between 1 and 65535",
        )
    return port


def load_secret(path: Path) -> bytes:
    encoded = path.read_text(encoding="ascii").strip()
    if len(encoded) != 43:
        raise ValueError("Secret file must contain one 43-character base64url value")
    return base64.urlsafe_b64decode(encoded + "=")


async def run(port: int, secret_path: Path) -> None:
    validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL_ROOT))
    gateway = LocalWebSocketGateway(
        validator=validator,
        state_machine=ProtocolStateMachine(secret=load_secret(secret_path)),
    )
    await gateway.start(port=port)
    print(f"AIA-JLCEDA gateway listening at {gateway.uri}")
    print("Only Phase 5B.1 handshake and heartbeat messages are enabled.")
    try:
        await asyncio.Future()
    finally:
        await gateway.stop()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run(args.port, args.secret_file.resolve()))
    except KeyboardInterrupt:
        print("Gateway stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
