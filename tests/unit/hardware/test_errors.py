from __future__ import annotations

import unittest

from ai_instrument_assistant.hardware.errors import (
    HardwareError,
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDisconnectedError,
    InstrumentIdentityMismatchError,
    InstrumentResponseError,
    InstrumentStateVerificationError,
    InstrumentTimeoutError,
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
    WaveformAcquisitionError,
    WaveformDecodeError,
    WaveformLengthMismatchError,
    WaveformMetadataError,
    WaveformProtocolError,
)


class HardwareErrorTests(unittest.TestCase):
    def test_phase6b_error_categories_share_one_provider_neutral_root(self) -> None:
        categories = (
            TransportError,
            InstrumentConnectionError,
            InstrumentDisconnectedError,
            InstrumentTimeoutError,
            InstrumentIdentityMismatchError,
            InstrumentCommandError,
            InstrumentResponseError,
            InstrumentStateVerificationError,
            WaveformAcquisitionError,
            WaveformProtocolError,
            WaveformDecodeError,
            WaveformMetadataError,
            WaveformLengthMismatchError,
        )
        for category in categories:
            with self.subTest(category=category.__name__):
                self.assertTrue(issubclass(category, HardwareError))
        self.assertTrue(issubclass(TransportTimeoutError, TransportError))
        self.assertTrue(issubclass(TransportDisconnectedError, TransportError))


if __name__ == "__main__":
    unittest.main()
