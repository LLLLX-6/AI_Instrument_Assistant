from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from ai_instrument_assistant.domain.eda.models import SelectionContext
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.remote_adapter import JLCEDARemoteAdapter
from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator

from run_jlceda_gateway import DEFAULT_SECRET_PATH, PROTOCOL_ROOT, load_secret, stable_port


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read one real JLCEDA selection through AIA-JLCEDA v1"
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
    print("In JLCEDA, configure the backend connection with the shared secret.")
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
        context = await adapter.get_selection()
        print(json.dumps(_selection_output(context), ensure_ascii=False, indent=2))
    finally:
        await gateway.stop()


def _selection_output(context: SelectionContext) -> dict[str, object]:
    selection = context.selection
    return {
        "observation_semantics": (
            "coherent AIA observation window; not an atomic provider revision"
        ),
        "document": {
            "provider": selection.document_ref.provider,
            "document_id": selection.document_ref.document_id,
            "snapshot_id": str(selection.document_ref.snapshot_id),
        },
        "selected_count": len(selection.selected_objects),
        "selected_objects": [
            {
                "object_type": selected.object_type.value,
                "provider_kind": selected.provider_kind,
                "native_id": selected.native_id,
                "canonical_id": selected.canonical_id,
                "display_name": selected.display_name,
                "snapshot_id": str(selected.snapshot_id),
            }
            for selected in selection.selected_objects
        ],
        "primary_object": None,
        "nets": [
            {
                "display_name": net.ref.display_name,
                "native_id": net.ref.native_id,
                "canonical_id": net.ref.canonical_id,
                "provider_kind": net.ref.provider_kind,
                "snapshot_id": str(net.ref.snapshot_id),
                "endpoint_count": len(net.endpoints),
                "connectivity_unresolved": net.connectivity_unresolved,
                "source": None,
                "signal_expectation": None,
            }
            for net in context.nets
        ],
    }


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Selection read cancelled.")
        return 130
    except Exception as error:
        print(f"Selection read failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
