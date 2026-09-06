from __future__ import annotations

import argparse
import json

from ai_instrument_assistant.analysis import analyze_waveform
from ai_instrument_assistant.drivers.rigol import DS1102ZEDriver
from ai_instrument_assistant.integrations.visa import PyVisaTransport


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare deterministic waveform analysis with DS1102Z-E queries."
    )
    parser.add_argument(
        "--resource",
        help="Exact discovered VISA resource; omit to list resources without connecting",
    )
    parser.add_argument("--channel", type=int, choices=(1, 2), default=1)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser.parse_args()


def mask_serial(value: str) -> str:
    return "****" if len(value) <= 4 else f"***{value[-4:]}"


def main() -> int:
    args = parse_args()
    print("Safety: USB control only. Do not probe mains or high voltage.")
    print("Use a safe low-voltage PWM source and confirm a common ground.")

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
        software = analyze_waveform(waveform)
        instrument_frequency = scope.measure_frequency(args.channel)
        instrument_vpp = scope.measure_vpp(args.channel)
        output = {
            "identity": {
                "manufacturer": identity.manufacturer,
                "model": identity.model,
                "serial_number": mask_serial(identity.serial_number),
                "firmware_version": identity.firmware_version,
            },
            "observation_note": (
                "Waveform capture and instrument queries are sequential, not one atomic record. "
                "No automatic accuracy pass/fail criterion is applied."
            ),
            "waveform": {
                "channel": waveform.channel,
                "point_count": waveform.point_count,
                "time_span_seconds": waveform.time_values[-1] - waveform.time_values[0],
                "sample_interval_seconds": waveform.sample_interval_seconds,
            },
            "instrument": {
                "frequency_hz": instrument_frequency,
                "vpp_v": instrument_vpp,
            },
            "software": {
                "vpp_v": software.vpp_v,
                "mean_v": software.mean_v,
                "rms_v": software.rms_v,
                "frequency_hz": software.frequency_hz,
                "period_s": software.period_s,
                "duty_cycle_ratio": (
                    None if software.duty_cycle is None else software.duty_cycle.ratio
                ),
                "duty_cycle_percent": (
                    None if software.duty_cycle is None else software.duty_cycle.percent
                ),
                "quality": software.quality.value,
                "warnings": [warning.value for warning in software.warnings],
                "algorithm": {
                    "name": software.algorithm.name,
                    "version": software.algorithm.version,
                    "threshold_strategy": software.algorithm.threshold_strategy,
                    "threshold_v": software.algorithm.threshold_v,
                    "hysteresis_strategy": software.algorithm.hysteresis_strategy,
                    "hysteresis_band_v": software.algorithm.hysteresis_band_v,
                    "rising_edge_count": software.algorithm.rising_edge_count,
                    "falling_edge_count": software.algorithm.falling_edge_count,
                    "periods_used": software.algorithm.periods_used,
                    "duty_cycles_used": software.algorithm.duty_cycles_used,
                },
            },
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        scope.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
