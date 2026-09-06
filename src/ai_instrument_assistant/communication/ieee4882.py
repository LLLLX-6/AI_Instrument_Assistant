from __future__ import annotations

from ai_instrument_assistant.hardware.errors import (
    WaveformLengthMismatchError,
    WaveformProtocolError,
)


def parse_definite_length_block(
    data: bytes,
    *,
    max_payload_bytes: int = 64 * 1024 * 1024,
) -> bytes:
    """Parse one IEEE 488.2 definite-length block without altering its payload."""

    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    if isinstance(max_payload_bytes, bool) or not isinstance(max_payload_bytes, int):
        raise TypeError("max_payload_bytes must be an integer")
    if max_payload_bytes < 0:
        raise ValueError("max_payload_bytes must not be negative")
    if len(data) < 2 or data[0:1] != b"#":
        raise WaveformProtocolError("Definite-length block header is missing")

    width_byte = data[1]
    if width_byte < ord("1") or width_byte > ord("9"):
        raise WaveformProtocolError("Indefinite or invalid block length is unsupported")
    width = width_byte - ord("0")
    header_end = 2 + width
    if len(data) < header_end:
        raise WaveformProtocolError("Definite-length block length field is truncated")

    length_field = data[2:header_end]
    if any(byte < ord("0") or byte > ord("9") for byte in length_field):
        raise WaveformProtocolError("Definite-length block length is not decimal")
    payload_length = int(length_field.decode("ascii"))
    if payload_length > max_payload_bytes:
        raise WaveformProtocolError("Declared waveform payload exceeds the application limit")

    payload_end = header_end + payload_length
    if len(data) < payload_end:
        raise WaveformLengthMismatchError("Waveform payload is shorter than declared")
    suffix = data[payload_end:]
    if suffix not in (b"", b"\n", b"\r\n"):
        raise WaveformProtocolError("Waveform block contains an unsupported trailing suffix")
    return data[header_end:payload_end]
