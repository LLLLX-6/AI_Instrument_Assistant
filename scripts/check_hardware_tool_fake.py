from __future__ import annotations

import json

from ai_instrument_assistant.bootstrap import build_fake_hardware_tool_composition


OPERATIONS = (
    ("hardware.get_status", {}),
    ("hardware.measure_frequency", {"channel": 1}),
    ("hardware.measure_vpp", {"channel": 1}),
    ("hardware.capture_waveform", {"channel": 1}),
    ("hardware.measure_pwm", {"channel": 1}),
)


def main() -> int:
    composition = build_fake_hardware_tool_composition()
    with composition:
        for operation, arguments in OPERATIONS:
            response = composition.runtime.execute({
                "contract_version": "1.0",
                "operation": operation,
                "arguments": arguments,
            })
            print(json.dumps(response, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
