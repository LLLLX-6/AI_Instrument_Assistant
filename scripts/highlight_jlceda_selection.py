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

from dataclasses import asdict, replace
from uuid import uuid4
from ai_instrument_assistant.application.ports.eda_interface import HighlightCommand, GuardMode, HighlightRejectedError, SubmissionStatus
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.remote_adapter import JLCEDARemoteAdapter
from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator

from run_jlceda_gateway import DEFAULT_SECRET_PATH, PROTOCOL_ROOT, load_secret, stable_port


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit guarded real JLCEDA highlight; acceptance does not prove visible rendering"
    )
    parser.add_argument("--port", type=stable_port, default=49624)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    parser.add_argument("--request-timeout", type=float, default=5.0)
    parser.add_argument("--weak-identity-check", action="store_true", help="Explicitly opt out of strong stale protection")
    parser.add_argument("--allow-scope-expansion", action="store_true", help="Explicitly permit wire-to-network expansion")
    parser.add_argument("--repeat", action="store_true", help="Send the SAME command through another adapter to exercise Extension deduplication")
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
        selection = context.selection
        if not selection.selected_objects:
            raise ValueError("Select at least one schematic object before running highlight")
        command = HighlightCommand(
            document_ref=selection.document_ref,
            expected_snapshot_id=selection.document_ref.snapshot_id,
            targets=selection.selected_objects,
            idempotency_key=str(uuid4()),
            guard_mode=GuardMode.WEAK_IDENTITY_CHECK if args.weak_identity_check else GuardMode.STRONG_REQUIRED,
            allow_scope_expansion=args.allow_scope_expansion,
        )
        print("Weak identity is NOT strong stale protection. Accepted is NOT visibly applied.")
        result = await adapter.highlight(command)
        print(json.dumps(asdict(result), default=str, ensure_ascii=False, indent=2))
        if args.repeat and result.submission_status is SubmissionStatus.INDETERMINATE:
            print("Repeat skipped: uncertain execution must not be replayed.")
        elif args.repeat:
            another = JLCEDARemoteAdapter(request_client=gateway, validator=validator,
                mapper=JLCEDADomainMapper(), request_timeout=args.request_timeout)
            repeated = await another.highlight(command)
            print("Second correlated wire request returned identical result:", repeated == result)
            try:
                await another.highlight(replace(command, allow_scope_expansion=not command.allow_scope_expansion))
            except HighlightRejectedError as error:
                print("Changed command rejected:", error.code)
    finally:
        await gateway.stop()


def main() -> int:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Highlight submission cancelled.")
        return 130
    except Exception as error:
        print(f"Highlight submission failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
