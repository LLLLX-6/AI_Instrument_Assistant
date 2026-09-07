from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Sequence

from ai_instrument_assistant.bootstrap.hardware_tool import HardwareBackend

from .composition import build_harness_hardware_backend
from .secret_store import (
    DEFAULT_SECRET_PATH,
    HarnessHardwareSecretStore,
    SecretStoreError,
)
from .server import DEFAULT_HOST, DEFAULT_PORT


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the authenticated local Harness Hardware backend."
    )
    parser.add_argument("--backend", choices=("fake", "real"), required=True)
    parser.add_argument("--host", type=_loopback_host, default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--resource")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--visa-backend")
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--initialize-secret", action="store_true")
    args = parser.parse_args(argv)
    if args.backend == "real" and not args.resource:
        parser.error("--resource is required when --backend real is selected")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    store = HarnessHardwareSecretStore(args.secret_file)
    try:
        if args.initialize_secret:
            store.bootstrap()
            print("Harness Hardware secret initialized.")
        asyncio.run(_run(args, store))
    except SecretStoreError:
        print("Harness Hardware secret is unavailable or invalid.")
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


async def _run(args: argparse.Namespace, store: HarnessHardwareSecretStore) -> None:
    backend = build_harness_hardware_backend(
        HardwareBackend(args.backend),
        secret_loader=store.load,
        port=args.port,
        resource_name=args.resource,
        timeout_seconds=args.timeout,
        visa_backend=args.visa_backend,
    )
    await backend.start()
    print(f"Harness Hardware backend ready at {backend.server.uri} ({args.backend}).")
    try:
        await asyncio.Future()
    finally:
        await backend.stop()


def _loopback_host(value: str) -> str:
    if value != DEFAULT_HOST:
        raise argparse.ArgumentTypeError("host must be exactly 127.0.0.1")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
