from __future__ import annotations

import unittest
from datetime import UTC, datetime

from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.domain.instrument.waveform import WaveformAcquisitionMode
from ai_instrument_assistant.drivers.rigol.waveform import (
    WaveformFormat,
    WaveformPreamble,
    WaveformReadingMode,
    parse_waveform_preamble,
    scale_norm_byte_waveform,
)
from ai_instrument_assistant.hardware.errors import (
    WaveformLengthMismatchError,
    WaveformMetadataError,
)


VALID = "0,0,3,1,1e-6,-2e-6,0,0.02,5,127"
IDENTITY = InstrumentIdentity("RIGOL", "DS1102Z-E", "SERIAL", "FW")


class RigolWaveformPreambleTests(unittest.TestCase):
    def test_verified_ten_field_order_maps_to_explicit_preamble(self) -> None:
        value = parse_waveform_preamble(VALID)
        self.assertIs(WaveformFormat.BYTE, value.format)
        self.assertIs(WaveformReadingMode.NORMAL, value.reading_mode)
        self.assertEqual(3, value.points)
        self.assertEqual(1, value.count)
        self.assertEqual(1e-6, value.x_increment)
        self.assertEqual(-2e-6, value.x_origin)
        self.assertEqual(0.0, value.x_reference)
        self.assertEqual(0.02, value.y_increment)
        self.assertEqual(5, value.y_origin)
        self.assertEqual(127, value.y_reference)

    def test_wrong_field_count_malformed_numeric_and_unknown_enum_are_rejected(self) -> None:
        cases = (
            "0,0,3,1,1e-6,-2e-6,0,0.02,5",
            "0,0,three,1,1e-6,-2e-6,0,0.02,5,127",
            "9,0,3,1,1e-6,-2e-6,0,0.02,5,127",
            "0,9,3,1,1e-6,-2e-6,0,0.02,5,127",
            "0,0,0,1,1e-6,-2e-6,0,0.02,5,127",
        )
        for response in cases:
            with self.subTest(response=response), self.assertRaises(WaveformMetadataError):
                parse_waveform_preamble(response)

    def test_scaling_uses_manual_byte_formula_without_uint8_underflow(self) -> None:
        preamble = parse_waveform_preamble(VALID)
        waveform = scale_norm_byte_waveform(
            preamble,
            bytes((122, 132, 142)),
            channel=1,
            requested_start=1,
            requested_stop=3,
            identity=IDENTITY,
            captured_at=datetime(2026, 9, 6, tzinfo=UTC),
        )
        for observed, expected in zip(waveform.voltage_values, (-0.2, 0.0, 0.2)):
            self.assertAlmostEqual(expected, observed)
        for observed, expected in zip(waveform.time_values, (-2e-6, -1e-6, 0.0)):
            self.assertAlmostEqual(expected, observed)
        self.assertIs(WaveformAcquisitionMode.NORMAL, waveform.acquisition_mode)

    def test_payload_and_preamble_point_count_must_match(self) -> None:
        with self.assertRaises(WaveformLengthMismatchError):
            scale_norm_byte_waveform(
                parse_waveform_preamble(VALID),
                bytes((122, 132)),
                channel=1,
                requested_start=1,
                requested_stop=3,
                identity=IDENTITY,
                captured_at=datetime(2026, 9, 6, tzinfo=UTC),
            )

    def test_first_slice_rejects_non_norm_byte_or_ambiguous_reference(self) -> None:
        values = (
            WaveformPreamble(WaveformFormat.WORD, WaveformReadingMode.NORMAL, 3, 1, 1e-6, 0, 0, .02, 0, 127),
            WaveformPreamble(WaveformFormat.BYTE, WaveformReadingMode.RAW, 3, 1, 1e-6, 0, 0, .02, 0, 127),
            WaveformPreamble(WaveformFormat.BYTE, WaveformReadingMode.NORMAL, 3, 1, 1e-6, 0, 1, .02, 0, 127),
            WaveformPreamble(WaveformFormat.BYTE, WaveformReadingMode.NORMAL, 3, 1, 1e-6, 0, 0, .02, 0, 128),
        )
        for preamble in values:
            with self.subTest(preamble=preamble), self.assertRaises(WaveformMetadataError):
                scale_norm_byte_waveform(
                    preamble, b"\x7f\x7f\x7f", channel=1,
                    requested_start=1, requested_stop=3, identity=IDENTITY,
                    captured_at=datetime(2026, 9, 6, tzinfo=UTC),
                )
        with self.assertRaises(WaveformMetadataError):
            scale_norm_byte_waveform(
                parse_waveform_preamble(VALID), b"\x7f\x7f\x7f", channel=1,
                requested_start=2, requested_stop=4, identity=IDENTITY,
                captured_at=datetime(2026, 9, 6, tzinfo=UTC),
            )


if __name__ == "__main__":
    unittest.main()
