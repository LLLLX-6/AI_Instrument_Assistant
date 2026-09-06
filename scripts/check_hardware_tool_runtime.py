from __future__ import annotations

import argparse
import copy
import json

from ai_instrument_assistant.bootstrap import build_real_hardware_tool_composition


OPERATIONS = (
    ("hardware.get_status", {}),
    ("hardware.measure_frequency", {"channel": 1}),
    ("hardware.measure_vpp", {"channel": 1}),
    ("hardware.capture_waveform", {"channel": 1}),
    ("hardware.measure_pwm", {"channel": 1}),
)


def request(operation: str, arguments: dict) -> dict:
    return {
        "contract_version": "1.0",
        "operation": operation,
        "arguments": arguments,
    }


def mask_serial_number(response: dict) -> dict:
    bounded = copy.deepcopy(response)
    instrument = bounded.get("result", {}).get("instrument")
    if isinstance(instrument, dict) and isinstance(instrument.get("serial_number"), str):
        serial = instrument["serial_number"]
        instrument["serial_number"] = f"***{serial[-4:]}" if len(serial) > 4 else "***"
    return bounded


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely smoke-test the real HardwareToolRuntime on CH1."
    )
    parser.add_argument("--resource", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--visa-backend")
    args = parser.parse_args()

    composition = build_real_hardware_tool_composition(
        args.resource,
        timeout_seconds=args.timeout,
        visa_backend=args.visa_backend,
    )
    try:
        composition.connect()
    except Exception:
        response = composition.runtime.execute(request("hardware.get_status", {}))
        print(json.dumps(mask_serial_number(response), indent=2))
        return 2

    try:
        for operation, arguments in OPERATIONS:
            response = composition.runtime.execute(request(operation, arguments))
            print(json.dumps(mask_serial_number(response), indent=2))
    finally:
        composition.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
