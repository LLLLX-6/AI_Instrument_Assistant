from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.domain.instrument.waveform import (
    Waveform,
    WaveformAcquisitionMode,
)


IDENTITY = InstrumentIdentity("RIGOL", "MODEL", "SERIAL", "FW")


class WaveformModelTests(unittest.TestCase):
    def test_provider_neutral_waveform_is_immutable_and_consistent(self) -> None:
        captured = datetime(2026, 9, 6, tzinfo=UTC)
        waveform = Waveform(
            channel=1,
            point_count=3,
            sample_interval_seconds=1e-6,
            time_origin_seconds=-2e-6,
            time_reference=0.0,
            voltage_increment=0.02,
            voltage_origin=5.0,
            voltage_reference=127.0,
            time_values=(-2e-6, -1e-6, 0.0),
            voltage_values=(-0.2, 0.0, 0.2),
            acquisition_mode=WaveformAcquisitionMode.NORMAL,
            instrument_identity=IDENTITY,
            captured_at=captured,
            average_count=1,
            requested_start=1,
            requested_stop=3,
        )
        self.assertEqual(3, waveform.point_count)
        self.assertEqual(0.4, max(waveform.voltage_values) - min(waveform.voltage_values))
        with self.assertRaises(FrozenInstanceError):
            waveform.point_count = 4  # type: ignore[misc]

    def test_waveform_rejects_length_and_metadata_inconsistency(self) -> None:
        base = dict(
            channel=1,
            point_count=2,
            sample_interval_seconds=1e-6,
            time_origin_seconds=0.0,
            time_reference=0.0,
            voltage_increment=0.02,
            voltage_origin=0.0,
            voltage_reference=127.0,
            time_values=(0.0,),
            voltage_values=(0.0, 0.1),
            acquisition_mode=WaveformAcquisitionMode.NORMAL,
            instrument_identity=IDENTITY,
            captured_at=datetime(2026, 9, 6, tzinfo=UTC),
            average_count=1,
            requested_start=1,
            requested_stop=2,
        )
        with self.assertRaises(ValueError):
            Waveform(**base)
        base["time_values"] = (0.0, 1e-6)
        base["captured_at"] = datetime(2026, 9, 6)
        with self.assertRaises(ValueError):
            Waveform(**base)


if __name__ == "__main__":
    unittest.main()
