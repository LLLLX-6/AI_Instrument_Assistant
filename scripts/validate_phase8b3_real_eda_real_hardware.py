from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
for path in (REPOSITORY_ROOT, SOURCE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ai_instrument_assistant.application.services.eda_design_evidence import (
    EDADesignEvidenceCaptureService,
)
from ai_instrument_assistant.bootstrap.hardware_tool import HardwareBackend
from ai_instrument_assistant.integrations.harness_hardware.composition import (
    build_harness_hardware_backend,
)
from ai_instrument_assistant.integrations.harness_hardware.secret_store import (
    HarnessHardwareSecretStore,
)
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.remote_adapter import JLCEDARemoteAdapter
from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator
from scripts.run_jlceda_gateway import DEFAULT_SECRET_PATH, PROTOCOL_ROOT, load_secret, stable_port
from validation.support.phase8b3.coordinator import Phase8B3Coordinator
from validation.support.phase8b3.host import BoundedCliHostInteraction
from validation.support.phase8b3.node_executor import (
    NodeGovernedHardwareExecutor,
    inherited_stdio_child_runner,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run explicitly authorized Phase 8B.3 real validation")
    parser.add_argument("--resource", required=True)
    parser.add_argument("--jlceda-port", type=stable_port, default=49624)
    parser.add_argument("--jlceda-secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--visa-backend")
    parser.add_argument("--instrument-timeout", type=float, default=5.0)
    parser.add_argument("--eda-connect-timeout", type=float, default=45.0)
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict[str, object]:
    validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL_ROOT))
    gateway = LocalWebSocketGateway(
        validator=validator,
        state_machine=ProtocolStateMachine(secret=load_secret(args.jlceda_secret_file.resolve())),
    )
    await gateway.start(port=args.jlceda_port)
    try:
        print("Phase 8B.3: connect JLCEDA and select the intended PWM_OUT wire.", file=sys.stderr)
        await _wait_for_eda(gateway, args.eda_connect_timeout)
        adapter = JLCEDARemoteAdapter(
            request_client=gateway,
            validator=validator,
            mapper=JLCEDADomainMapper(),
        )
        capture = EDADesignEvidenceCaptureService(eda=adapter)
        secret_store = HarnessHardwareSecretStore(
            REPOSITORY_ROOT / ".aia-secrets" / "harness-hardware-psk.txt"
        )
        hardware = NodeGovernedHardwareExecutor(
            backend_factory=lambda: build_harness_hardware_backend(
                HardwareBackend.REAL,
                secret_loader=secret_store.load,
                port=49625,
                resource_name=args.resource,
                timeout_seconds=args.instrument_timeout,
                visa_backend=args.visa_backend,
            ),
            child_runner=inherited_stdio_child_runner(repository_root=REPOSITORY_ROOT),
        )
        result = await Phase8B3Coordinator(
            capture=capture,
            host=BoundedCliHostInteraction(),
            hardware=hardware,
            repository_root=REPOSITORY_ROOT,
        ).run()
        return result.to_bounded_output()
    finally:
        await gateway.stop()


async def _wait_for_eda(gateway: LocalWebSocketGateway, timeout: float) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while gateway.authenticated_session_count != 1:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("bounded EDA authentication wait expired")
        await asyncio.sleep(0.1)


def main() -> int:
    try:
        output = asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        output = {"status": "NOT_PASS", "phase": "8B.3", "failure": {"stage": "runner", "code": "cancelled"}}
    except Exception:
        output = {"status": "NOT_PASS", "phase": "8B.3", "failure": {"stage": "runner", "code": "bounded_failure"}}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
