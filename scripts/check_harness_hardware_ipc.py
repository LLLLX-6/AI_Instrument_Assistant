from __future__ import annotations

import argparse
import asyncio
import json
import secrets
from typing import Any

from ai_instrument_assistant.bootstrap.hardware_tool import HardwareBackend
from ai_instrument_assistant.integrations.harness_hardware.composition import (
    build_harness_hardware_backend,
)
from ai_instrument_assistant.integrations.harness_hardware.dev_client import (
    HarnessHardwareDevClient,
)


OPERATIONS = (
    ("hardware.get_status", {}),
    ("hardware.measure_frequency", {"channel": 1}),
    ("hardware.measure_vpp", {"channel": 1}),
    ("hardware.capture_waveform", {"channel": 1}),
    ("hardware.measure_pwm", {"channel": 1}),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test Harness Hardware IPC using only the fake backend."
    )
    parser.add_argument("--port", type=int, default=0)
    return parser.parse_args()


async def run(port: int) -> list[dict[str, Any]]:
    secret = secrets.token_bytes(32)
    backend = build_harness_hardware_backend(
        HardwareBackend.FAKE,
        secret_loader=lambda: secret,
        port=port,
    )
    await backend.start()
    client = HarnessHardwareDevClient(backend.server.uri, secret)
    try:
        await client.connect_and_authenticate()
        summaries: list[dict[str, Any]] = []
        for operation, arguments in OPERATIONS:
            response = await client.request(operation, arguments)
            result = response["hardware_result"]
            summary: dict[str, Any] = {
                "operation": operation,
                "message_type": response["type"],
                "ok": result["ok"],
            }
            if result["ok"] and isinstance(result.get("result"), dict):
                summary["quality"] = result["result"].get("quality")
                waveform = result["result"].get("waveform")
                if isinstance(waveform, dict):
                    artifact = waveform.get("artifact")
                    if isinstance(artifact, dict):
                        summary["artifact"] = {
                            "artifact_id": artifact.get("artifact_id"),
                            "uri": artifact.get("uri"),
                            "media_type": artifact.get("media_type"),
                        }
            summaries.append(summary)
        return summaries
    finally:
        await client.close()
        await backend.stop()


def main() -> int:
    args = parse_args()
    summaries = asyncio.run(run(args.port))
    print(json.dumps({"backend": "fake", "results": summaries}, indent=2))
    return 0 if len(summaries) == len(OPERATIONS) and all(
        item["message_type"] == "response" for item in summaries
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
