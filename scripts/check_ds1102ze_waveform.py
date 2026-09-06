from __future__ import annotations

import argparse
import json
import math

from ai_instrument_assistant.drivers.rigol import DS1102ZEDriver
from ai_instrument_assistant.integrations.visa import PyVisaTransport


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manually validate one DS1102Z-E NORM/BYTE screen-waveform capture."
    )
    parser.add_argument(
        "--resource",
        help="Exact discovered VISA resource; omit to list resources without connecting",
    )
    parser.add_argument("--channel", type=int, choices=(1, 2), default=1)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser.parse_args()


def mask_serial(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return f"***{value[-4:]}"


def main() -> int:
    args = parse_args()
    print("Safety: USB control only. Do not probe mains or high voltage.")
    print("Use a safe low-voltage source and confirm a common ground before capture.")

    transport = PyVisaTransport()
    resources = transport.discover_resources()
    print(json.dumps({"discovered_resources": resources}, ensure_ascii=False, indent=2))
    if args.resource is None:
        return 0
    if args.resource not in resources:
        print("The selected VISA resource was not present in this discovery result.")
        return 2

    scope = DS1102ZEDriver(
        transport,
        args.resource,
        timeout_seconds=args.timeout,
    )
    try:
        identity = scope.connect()
        waveform = scope.capture_waveform(args.channel)
        minimum = min(waveform.voltage_values)
        maximum = max(waveform.voltage_values)
        summary = {
            "identity": {
                "manufacturer": identity.manufacturer,
                "model": identity.model,
                "serial_number": mask_serial(identity.serial_number),
                "firmware_version": identity.firmware_version,
            },
            "waveform": {
                "channel": waveform.channel,
                "point_count": waveform.point_count,
                "sample_interval_seconds": waveform.sample_interval_seconds,
                "time_origin_seconds": waveform.time_origin_seconds,
                "minimum_voltage": minimum,
                "maximum_voltage": maximum,
                "observed_voltage_span": maximum - minimum,
                "all_samples_finite": all(
                    math.isfinite(value)
                    for value in waveform.time_values + waveform.voltage_values
                ),
                "first_samples": [
                    {"time_seconds": time_value, "voltage": voltage_value}
                    for time_value, voltage_value in zip(
                        waveform.time_values[:8], waveform.voltage_values[:8]
                    )
                ],
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        scope.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
