from __future__ import annotations

import unittest
from unittest.mock import patch

from ai_instrument_assistant.bootstrap.hardware_tool import (
    HardwareBackend,
    build_fake_hardware_tool_composition,
    build_hardware_tool_composition,
    build_real_hardware_tool_composition,
)
from ai_instrument_assistant.hardware.errors import InstrumentConnectionError
from tests.support.recorded_visa import RecordedVisaConnection, RecordedVisaTransport
from tests.unit.bootstrap.test_measurement_runtime import (
    IDN,
    PREAMBLE,
    RESOURCE,
    block,
    pwm_payload,
)


def recorded_transport() -> RecordedVisaTransport:
    return RecordedVisaTransport(RecordedVisaConnection(
        responses={
            "*IDN?": IDN,
            ":WAVeform:SOURce?": "CHAN1",
            ":WAVeform:MODE?": "NORM",
            ":WAVeform:FORMat?": "BYTE",
            ":WAVeform:STARt?": "1",
            ":WAVeform:STOP?": "1200",
            ":WAVeform:PREamble?": PREAMBLE,
            ":MEASure:ITEM? FREQuency,CHANnel1": "10020.04",
            ":MEASure:ITEM? VPP,CHANnel1": "0.424",
        },
        raw_response=block(pwm_payload()),
    ))


class HardwareToolCompositionTests(unittest.TestCase):
    def test_fake_and_real_recorded_compositions_share_response_contract(self) -> None:
        fake = build_fake_hardware_tool_composition()
        real = build_real_hardware_tool_composition(
            RESOURCE,
            transport=recorded_transport(),
        )
        requests = (
            {
                "contract_version": "1.0",
                "operation": "hardware.get_status",
                "arguments": {},
            },
            *(
                {
                    "contract_version": "1.0",
                    "operation": operation,
                    "arguments": {"channel": 1},
                }
                for operation in (
                    "hardware.measure_frequency",
                    "hardware.measure_vpp",
                    "hardware.capture_waveform",
                    "hardware.measure_pwm",
                )
            ),
        )
        with fake, real:
            pairs = tuple(
                (fake.runtime.execute(request), real.runtime.execute(request))
                for request in requests
            )
        for fake_response, real_response in pairs:
            with self.subTest(operation=fake_response["operation"]):
                self.assertTrue(fake_response["ok"])
                self.assertTrue(real_response["ok"])
                self.assertEqual(set(fake_response), set(real_response))
                self.assertEqual(set(fake_response["result"]), set(real_response["result"]))
        fake_pwm, real_pwm = pairs[-1]
        self.assertEqual(
            "simulated",
            fake_pwm["result"]["observations"]["instrument_frequency"]["source"],
        )
        self.assertEqual(
            "instrument",
            real_pwm["result"]["observations"]["instrument_frequency"]["source"],
        )

    def test_backend_selection_is_explicit_and_real_never_falls_back(self) -> None:
        fake = build_hardware_tool_composition(HardwareBackend.FAKE)
        self.assertIs(HardwareBackend.FAKE, fake.backend)
        with self.assertRaises(ValueError):
            build_hardware_tool_composition(HardwareBackend.REAL)

        failing = RecordedVisaTransport(
            RecordedVisaConnection(),
            open_error=InstrumentConnectionError("unavailable"),
        )
        composition = build_real_hardware_tool_composition(
            RESOURCE,
            transport=failing,
        )
        with patch(
            "ai_instrument_assistant.bootstrap.hardware_tool.build_fake_hardware_tool_composition"
        ) as fake_builder:
            with self.assertRaises(InstrumentConnectionError):
                composition.connect()
            fake_builder.assert_not_called()


if __name__ == "__main__":
    unittest.main()
