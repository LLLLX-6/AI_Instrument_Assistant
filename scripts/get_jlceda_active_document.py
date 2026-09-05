from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.remote_adapter import JLCEDARemoteAdapter
from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator

from run_jlceda_gateway import DEFAULT_SECRET_PATH, PROTOCOL_ROOT, load_secret, stable_port


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read one real active JLCEDA document through AIA-JLCEDA v1"
    )
    parser.add_argument("--port", type=stable_port, default=49624)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    if args.connect_timeout <= 0 or args.request_timeout <= 0:
        raise ValueError("timeouts must be positive")
    validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL_ROOT))
    gateway = LocalWebSocketGateway(
        validator=validator,
        state_machine=ProtocolStateMachine(secret=load_secret(args.secret_file.resolve())),
    )
    await gateway.start(port=args.port)
    print(f"AIA-JLCEDA gateway listening at {gateway.uri}")
    print("In JLCEDA, choose Configure Backend Connection and enter the shared secret.")
    try:
        deadline = asyncio.get_running_loop().time() + args.connect_timeout
        while gateway.authenticated_session_count != 1:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("No authenticated JLCEDA Extension connected in time")
            await asyncio.sleep(0.1)
        adapter = JLCEDARemoteAdapter(
            request_client=gateway,
            validator=validator,
            mapper=JLCEDADomainMapper(),
            request_timeout=args.request_timeout,
        )
        document = await adapter.get_active_document()
        print(json.dumps(_document_output(document), ensure_ascii=False, indent=2))
    finally:
        await gateway.stop()


def _document_output(document: object) -> dict[str, object]:
    ref = getattr(document, "document_ref")
    captured_at: datetime = getattr(document, "captured_at")
    return {
        "provider": ref.provider,
        "document_id": ref.document_id,
        "native_id": ref.native_id,
        "canonical_id": ref.canonical_id,
        "display_name": ref.display_name,
        "snapshot_id": str(ref.snapshot_id),
        "project_id": getattr(document, "project_id"),
        "project_name": getattr(document, "project_name"),
        "document_name": getattr(document, "document_name"),
        "document_type": getattr(document, "document_type"),
        "native_revision": getattr(document, "native_revision"),
        "fingerprint": None,
        "is_dirty": getattr(document, "is_dirty"),
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(),
    }


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Active-document read cancelled.")
        return 130
    except Exception as error:
        print(f"Active-document read failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
