from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from ai_instrument_assistant.drivers.rigol.ds1102ze import DS1102ZEDriver  # noqa: E402
from ai_instrument_assistant.hardware.errors import HardwareError  # noqa: E402
from ai_instrument_assistant.integrations.visa.pyvisa_transport import PyVisaTransport  # noqa: E402


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual, bounded DS1102Z-E Phase 6B HIL spot check."
    )
    parser.add_argument(
        "--resource",
        help="Exact discovered VISA resource; omit to list resources without connecting",
    )
    parser.add_argument("--backend", help="Optional PyVISA backend, for example @ivi")
    parser.add_argument("--channel", type=int, choices=(1, 2), default=1)
    parser.add_argument(
        "--verify-write",
        action="store_true",
        help="Set channel enabled=true, verify it, then restore the original value",
    )
    parser.add_argument(
        "--measure",
        action="store_true",
        help="Query frequency and Vpp after connecting a known safe low-voltage signal",
    )
    parser.add_argument(
        "--show-serial",
        action="store_true",
        help="Print the full serial number instead of a masked value",
    )
    return parser.parse_args()


def _masked_serial(serial: str, show: bool) -> str:
    if show or len(serial) <= 4:
        return serial
    return f"***{serial[-4:]}"


def main() -> int:
    args = _arguments()
    print("Safety: USB control only. Do not probe mains or high voltage.")
    if args.measure:
        print("Measurement requires a safe low-voltage source and confirmed common ground.")

    try:
        transport = PyVisaTransport(backend=args.backend)
        resources = transport.discover_resources()
        print(json.dumps({"discovered_resources": resources}, ensure_ascii=False, indent=2))
        if args.resource is None:
            if args.verify_write or args.measure:
                print("--verify-write and --measure require --resource.", file=sys.stderr)
                return 2
            return 0
        if args.resource not in resources:
            print("The selected VISA resource was not present in this discovery result.")
            return 2

        scope = DS1102ZEDriver(
            transport,
            args.resource,
            timeout_seconds=3.0,
        )
        scope.connect()
        try:
            identity = scope.get_identity()
            settings = {
                "channel": args.channel,
                "enabled": scope.get_channel_enabled(args.channel),
                "coupling": scope.get_channel_coupling(args.channel).value,
                "scale_volts_per_div": scope.get_channel_scale(args.channel),
                "probe_ratio": scope.get_probe_ratio(args.channel),
                "timebase_seconds_per_div": scope.get_timebase_scale(),
            }
            print(json.dumps({
                "identity": {
                    "manufacturer": identity.manufacturer,
                    "model": identity.model,
                    "serial_number": _masked_serial(
                        identity.serial_number, args.show_serial
                    ),
                    "firmware_version": identity.firmware_version,
                },
                "settings": settings,
            }, ensure_ascii=False, indent=2))

            if args.verify_write:
                original_enabled = settings["enabled"]
                try:
                    scope.set_channel_enabled(args.channel, True)
                    print(json.dumps({
                        "safe_write_verification": "passed",
                        "test_value": True,
                    }, indent=2))
                finally:
                    scope.set_channel_enabled(args.channel, bool(original_enabled))
                restored = scope.get_channel_enabled(args.channel)
                if restored is not original_enabled:
                    raise HardwareError("Channel enabled state was not restored")
                print(json.dumps({"restore_verification": "passed"}, indent=2))

            if args.measure:
                print(json.dumps({
                    "measurement": {
                        "channel": args.channel,
                        "frequency_hz": scope.measure_frequency(args.channel),
                        "vpp_v": scope.measure_vpp(args.channel),
                    }
                }, ensure_ascii=False, indent=2))
        finally:
            scope.disconnect()
    except HardwareError as error:
        print(f"HIL check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
