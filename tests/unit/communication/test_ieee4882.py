from __future__ import annotations

import unittest

from ai_instrument_assistant.communication.ieee4882 import parse_definite_length_block
from ai_instrument_assistant.hardware.errors import (
    WaveformLengthMismatchError,
    WaveformProtocolError,
)


class DefiniteLengthBlockTests(unittest.TestCase):
    def test_valid_n1_n2_and_n9_blocks_return_exact_payload(self) -> None:
        cases = (
            (b"#13abc", b"abc"),
            (b"#212abcdefghijkl", b"abcdefghijkl"),
            (b"#9000000003\x00\x0a\xff", b"\x00\x0a\xff"),
        )
        for block, expected in cases:
            with self.subTest(block=block[:12]):
                self.assertEqual(expected, parse_definite_length_block(block))

    def test_zero_and_non_digit_length_field_width_are_rejected(self) -> None:
        for block in (b"#0payload", b"#x123", b"", b"x13abc"):
            with self.subTest(block=block), self.assertRaises(WaveformProtocolError):
                parse_definite_length_block(block)

    def test_malformed_or_truncated_length_field_is_rejected(self) -> None:
        for block in (b"#2", b"#21", b"#2a1payload"):
            with self.subTest(block=block), self.assertRaises(WaveformProtocolError):
                parse_definite_length_block(block)

    def test_truncated_payload_has_specific_length_mismatch(self) -> None:
        with self.assertRaises(WaveformLengthMismatchError):
            parse_definite_length_block(b"#15abcd")

    def test_only_no_terminator_lf_or_crlf_are_accepted(self) -> None:
        for suffix in (b"", b"\n", b"\r\n"):
            self.assertEqual(b"abc", parse_definite_length_block(b"#13abc" + suffix))
        for suffix in (b"x", b"\r", b"\nextra"):
            with self.subTest(suffix=suffix), self.assertRaises(WaveformProtocolError):
                parse_definite_length_block(b"#13abc" + suffix)

    def test_empty_definite_payload_is_valid_at_generic_protocol_layer(self) -> None:
        self.assertEqual(b"", parse_definite_length_block(b"#10"))

    def test_declared_large_payload_is_parsed_without_fixed_header_assumption(self) -> None:
        payload = bytes(range(256)) * 1024
        block = b"#9" + f"{len(payload):09d}".encode("ascii") + payload
        self.assertEqual(payload, parse_definite_length_block(block))

    def test_application_payload_limit_is_checked_before_payload_access(self) -> None:
        with self.assertRaises(WaveformProtocolError):
            parse_definite_length_block(b"#908388608", max_payload_bytes=64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
