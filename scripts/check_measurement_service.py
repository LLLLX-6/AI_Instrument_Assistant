from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator, ValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from ai_instrument_assistant.application.tool_contracts import (  # noqa: E402
    serialize_instrument_status,
    serialize_measurement_result,
)
from ai_instrument_assistant.bootstrap import (  # noqa: E402
    MeasurementRuntime,
    build_ds1102ze_measurement_runtime,
    discover_visa_resources,
)
from ai_instrument_assistant.domain.instrument import HardwareError  # noqa: E402
from ai_instrument_assistant.domain.measurement import (  # noqa: E402
    MeasurementKind,
    MeasurementQuality,
    MeasurementRequest,
    MeasurementResult,
)


SCHEMA_PATH = REPOSITORY_ROOT / "protocols/hardware/v1/hardware-tool.schema.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the real MeasurementService workflow with a DS1102Z-E."
    )
    parser.add_argument(
        "--resource",
        help="Exact discovered VISA resource; omit to list resources without connecting",
    )
    parser.add_argument("--backend", help="Optional PyVISA backend, for example @ivi")
    parser.add_argument("--channel", type=int, choices=(1, 2), default=1)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("Safety: USB control only. Do not probe mains or high voltage.")
    print("Use a safe low-voltage PWM source and confirm a common ground.")
    try:
        resources = discover_visa_resources(backend=args.backend)
        print(json.dumps({"discovered_resources": resources}, ensure_ascii=False, indent=2))
        if args.resource is None:
            return 0
        if args.resource not in resources:
            print("The selected VISA resource was not present in this discovery result.")
            return 2

        runtime = build_ds1102ze_measurement_runtime(
            args.resource,
            timeout_seconds=args.timeout,
            backend=args.backend,
        )
        with runtime:
            summary, accepted = _run_scenarios(runtime, args.channel)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if accepted else 1
    except ValidationError:
        print("MeasurementService result failed the Hardware Tool schema.", file=sys.stderr)
        return 1
    except (HardwareError, ValueError) as error:
        print(f"MeasurementService HIL failed: {error}", file=sys.stderr)
        return 1


def _run_scenarios(
    runtime: MeasurementRuntime,
    channel: int,
) -> tuple[dict[str, Any], bool]:
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    status = _mask_serial(serialize_instrument_status(runtime.service.get_status()))
    validator.validate(status)

    results = {
        kind.value: runtime.service.measure(MeasurementRequest(
            request_id=uuid4(),
            kind=kind,
            channel=channel,
            context_id="phase6f-real-hil",
        ))
        for kind in (
            MeasurementKind.FREQUENCY,
            MeasurementKind.VPP,
            MeasurementKind.WAVEFORM,
            MeasurementKind.PWM,
        )
    }
    payloads: dict[str, dict[str, Any]] = {}
    for name, result in results.items():
        payload = _mask_serial(serialize_measurement_result(result))
        validator.validate(payload)
        payloads[name] = payload

    waveform_check = _verify_artifact(runtime, results[MeasurementKind.WAVEFORM.value])
    pwm_check = _verify_artifact(runtime, results[MeasurementKind.PWM.value])
    pwm = results[MeasurementKind.PWM.value]
    accepted = (
        all(result.quality is not MeasurementQuality.FAILED for result in results.values())
        and pwm.quality is MeasurementQuality.GOOD
        and waveform_check["verified"]
        and pwm_check["verified"]
    )
    return {
        "status": status,
        "measurements": payloads,
        "artifact_verification": {
            "waveform": waveform_check,
            "pwm": pwm_check,
        },
        "pwm_workflow_order": [
            "capture_waveform",
            "deterministic_analysis",
            "instrument_frequency_query",
            "instrument_vpp_query",
        ],
        "observation_note": (
            "Software observations share one waveform artifact. Instrument queries occur "
            "after capture in the same session and are not atomic or simultaneous. No "
            "instrument/software accuracy pass criterion is applied."
        ),
        "hil_acceptance": "ready_for_manual_review" if accepted else "not_accepted",
    }, accepted


def _verify_artifact(
    runtime: MeasurementRuntime,
    result: MeasurementResult,
) -> dict[str, Any]:
    if result.waveform is None:
        return {"verified": False, "reason": "waveform_artifact_unavailable"}
    stored = runtime.artifact_store.get(result.waveform.reference)
    if stored is None:
        return {"verified": False, "reason": "artifact_not_found"}
    metadata_matches = (
        stored.channel == result.waveform.channel
        and stored.point_count == result.waveform.point_count
        and stored.sample_interval_seconds == result.waveform.sample_interval_seconds
        and stored.acquisition_mode.value == result.waveform.acquisition_mode
        and stored.captured_at == result.waveform.captured_at
    )
    return {
        "verified": metadata_matches,
        "artifact_id": str(result.waveform.reference.artifact_id),
        "uri": result.waveform.reference.uri,
        "channel": result.waveform.channel,
        "point_count": result.waveform.point_count,
        "sample_interval_seconds": result.waveform.sample_interval_seconds,
        "metadata_matches_stored_waveform": metadata_matches,
        "durability": "process_local_non_durable",
    }


def _mask_serial(payload: dict[str, Any]) -> dict[str, Any]:
    masked = copy.deepcopy(payload)
    result = masked.get("result")
    if isinstance(result, dict):
        instrument = result.get("instrument")
        if isinstance(instrument, dict):
            serial = instrument.get("serial_number")
            if isinstance(serial, str):
                instrument["serial_number"] = (
                    "****" if len(serial) <= 4 else f"***{serial[-4:]}"
                )
    return masked


if __name__ == "__main__":
    raise SystemExit(main())
