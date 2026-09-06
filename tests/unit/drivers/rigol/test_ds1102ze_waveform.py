from __future__ import annotations

import unittest

from ai_instrument_assistant.drivers.rigol.ds1102ze import DS1102ZEDriver
from ai_instrument_assistant.hardware.errors import (
    InstrumentDisconnectedError,
    InstrumentStateVerificationError,
    WaveformLengthMismatchError,
    WaveformMetadataError,
    WaveformProtocolError,
)
from tests.support.recorded_visa import RecordedVisaConnection, RecordedVisaTransport


RESOURCE = "USB0::0x1AB1::0x04CE::DS1ZA000000000::INSTR"
IDN = "RIGOL TECHNOLOGIES,DS1102Z-E,DS1ZA000000000,00.06.02"
PAYLOAD = bytes(range(256)) * 4 + bytes(range(176))
PREAMBLE = "0,0,1200,1,2e-7,-0.00012,0,0.002,0,127"


def block(payload: bytes = PAYLOAD) -> bytes:
    return b"#9" + f"{len(payload):09d}".encode("ascii") + payload + b"\n"


def connected_driver(
    responses: dict[str, str | list[str]],
    *,
    raw_response: bytes = block(),
    connection_type: type[RecordedVisaConnection] = RecordedVisaConnection,
) -> tuple[DS1102ZEDriver, RecordedVisaConnection]:
    connection = connection_type(
        responses={"*IDN?": IDN, **responses},
        raw_response=raw_response,
    )
    scope = DS1102ZEDriver(
        RecordedVisaTransport(connection), RESOURCE, timeout_seconds=2.0
    )
    scope.connect()
    connection.calls.clear()
    return scope, connection


TARGET_RESPONSES: dict[str, str | list[str]] = {
    ":WAVeform:SOURce?": "CHAN1",
    ":WAVeform:MODE?": "NORM",
    ":WAVeform:FORMat?": "BYTE",
    ":WAVeform:STARt?": "1",
    ":WAVeform:STOP?": "1200",
    ":WAVeform:PREamble?": PREAMBLE,
}


class DS1102ZEWaveformTests(unittest.TestCase):
    def test_norm_byte_capture_scales_1200_points_without_changing_acquisition(self) -> None:
        scope, connection = connected_driver(TARGET_RESPONSES)

        waveform = scope.capture_waveform(1)

        self.assertEqual(1200, waveform.point_count)
        self.assertEqual(1, waveform.channel)
        self.assertAlmostEqual(-0.254, waveform.voltage_values[0])
        self.assertAlmostEqual(-0.00012, waveform.time_values[0])
        self.assertAlmostEqual(-0.00012 + 1199 * 2e-7, waveform.time_values[-1])
        self.assertNotIn(("write", ":STOP"), connection.calls)
        self.assertNotIn(("write", ":RUN"), connection.calls)
        self.assertEqual(("write", ":WAVeform:DATA?"), connection.calls[-2])
        self.assertEqual(("read_raw", ""), connection.calls[-1])

    def test_changed_waveform_state_is_verified_and_restored_in_reverse_order(self) -> None:
        responses: dict[str, str | list[str]] = {
            ":WAVeform:SOURce?": ["CHAN2", "CHAN1", "CHAN2"],
            ":WAVeform:MODE?": ["MAX", "NORM", "MAX"],
            ":WAVeform:FORMat?": ["WORD", "BYTE", "WORD"],
            ":WAVeform:STARt?": ["100", "1", "100"],
            ":WAVeform:STOP?": ["500", "1200", "500"],
            ":WAVeform:PREamble?": PREAMBLE,
        }
        scope, connection = connected_driver(responses)

        scope.capture_waveform(1)

        writes = [command for operation, command in connection.calls if operation == "write"]
        self.assertEqual([
            ":WAVeform:SOURce CHANnel1",
            ":WAVeform:MODE NORM",
            ":WAVeform:FORMat BYTE",
            ":WAVeform:STARt 1",
            ":WAVeform:STOP 1200",
            ":WAVeform:DATA?",
            ":WAVeform:STOP 500",
            ":WAVeform:STARt 100",
            ":WAVeform:FORMat WORD",
            ":WAVeform:MODE MAX",
            ":WAVeform:SOURce CHANnel2",
        ], writes)

    def test_capture_failure_still_restores_changed_waveform_state(self) -> None:
        responses: dict[str, str | list[str]] = {
            ":WAVeform:SOURce?": ["CHAN2", "CHAN1", "CHAN2"],
            ":WAVeform:MODE?": "NORM",
            ":WAVeform:FORMat?": "BYTE",
            ":WAVeform:STARt?": "1",
            ":WAVeform:STOP?": "1200",
            ":WAVeform:PREamble?": PREAMBLE,
        }
        scope, connection = connected_driver(responses, raw_response=b"not-a-block")

        with self.assertRaises(WaveformProtocolError):
            scope.capture_waveform(1)

        self.assertEqual(("write", ":WAVeform:SOURce CHANnel2"), connection.calls[-2])
        self.assertEqual(("query", ":WAVeform:SOURce?"), connection.calls[-1])

    def test_failed_setup_readback_still_attempts_original_state_restore(self) -> None:
        responses = {
            **TARGET_RESPONSES,
            ":WAVeform:SOURce?": ["CHAN2", "CHAN2", "CHAN2"],
        }
        scope, connection = connected_driver(responses)

        with self.assertRaises(InstrumentStateVerificationError):
            scope.capture_waveform(1)

        self.assertEqual([
            ("write", ":WAVeform:SOURce CHANnel1"),
            ("write", ":WAVeform:SOURce CHANnel2"),
        ], [call for call in connection.calls if call[0] == "write"])

    def test_malformed_preamble_and_payload_length_have_specific_errors(self) -> None:
        cases = (
            ({**TARGET_RESPONSES, ":WAVeform:PREamble?": "0,0,bad"}, block(), WaveformMetadataError),
            (TARGET_RESPONSES, b"#9000001200" + PAYLOAD[:-1], WaveformLengthMismatchError),
        )
        for responses, raw_response, expected in cases:
            scope, _ = connected_driver(responses, raw_response=raw_response)
            with self.subTest(expected=expected.__name__), self.assertRaises(expected):
                scope.capture_waveform(1)

    def test_binary_transport_disconnect_remains_transport_semantics(self) -> None:
        class DisconnectingConnection(RecordedVisaConnection):
            def read_raw(self) -> bytes:
                self.calls.append(("read_raw", ""))
                raise ConnectionError("private backend detail")

        scope, _ = connected_driver(
            TARGET_RESPONSES,
            connection_type=DisconnectingConnection,
        )
        with self.assertRaises(InstrumentDisconnectedError) as raised:
            scope.capture_waveform(1)
        self.assertNotIn("private backend detail", str(raised.exception))

    def test_invalid_channel_is_rejected_before_transport_io(self) -> None:
        connection = RecordedVisaConnection(responses={"*IDN?": IDN})
        scope = DS1102ZEDriver(
            RecordedVisaTransport(connection), RESOURCE, timeout_seconds=2.0
        )
        for channel in (0, 3):
            with self.subTest(channel=channel), self.assertRaises(ValueError):
                scope.capture_waveform(channel)
        self.assertEqual([], connection.calls)


if __name__ == "__main__":
    unittest.main()
