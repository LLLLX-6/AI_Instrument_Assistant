from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.domain.instrument.waveform import (
    Waveform,
    WaveformAcquisitionMode,
)
from ai_instrument_assistant.hardware.errors import (
    WaveformLengthMismatchError,
    WaveformMetadataError,
)


class WaveformFormat(IntEnum):
    BYTE = 0
    WORD = 1
    ASCII = 2


class WaveformReadingMode(IntEnum):
    NORMAL = 0
    MAXIMUM = 1
    RAW = 2


@dataclass(frozen=True, slots=True)
class WaveformPreamble:
    format: WaveformFormat
    reading_mode: WaveformReadingMode
    points: int
    count: int
    x_increment: float
    x_origin: float
    x_reference: float
    y_increment: float
    y_origin: float
    y_reference: float

    def __post_init__(self) -> None:
        if not isinstance(self.format, WaveformFormat):
            raise WaveformMetadataError("Waveform format is unsupported")
        if not isinstance(self.reading_mode, WaveformReadingMode):
            raise WaveformMetadataError("Waveform reading mode is unsupported")
        if isinstance(self.points, bool) or not isinstance(self.points, int) or self.points < 1:
            raise WaveformMetadataError("Waveform point count must be positive")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 1:
            raise WaveformMetadataError("Waveform average count must be positive")
        for field, value in (
            ("x_increment", self.x_increment),
            ("x_origin", self.x_origin),
            ("x_reference", self.x_reference),
            ("y_increment", self.y_increment),
            ("y_origin", self.y_origin),
            ("y_reference", self.y_reference),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise WaveformMetadataError(f"{field} must be finite")
        if self.x_increment <= 0 or self.y_increment <= 0:
            raise WaveformMetadataError("Waveform increments must be positive")


def parse_waveform_preamble(response: str) -> WaveformPreamble:
    """Parse the verified ten-field DS1000Z-E :WAVeform:PREamble order."""

    if not isinstance(response, str):
        raise WaveformMetadataError("Waveform preamble must be text")
    fields = tuple(field.strip() for field in response.split(","))
    if len(fields) != 10:
        raise WaveformMetadataError("Waveform preamble must contain ten fields")
    try:
        preamble = WaveformPreamble(
            format=WaveformFormat(int(fields[0])),
            reading_mode=WaveformReadingMode(int(fields[1])),
            points=int(fields[2]),
            count=int(fields[3]),
            x_increment=float(fields[4]),
            x_origin=float(fields[5]),
            x_reference=float(fields[6]),
            y_increment=float(fields[7]),
            y_origin=float(fields[8]),
            y_reference=float(fields[9]),
        )
    except (ValueError, TypeError) as error:
        raise WaveformMetadataError("Waveform preamble contains invalid values") from error
    return preamble


def scale_norm_byte_waveform(
    preamble: WaveformPreamble,
    payload: bytes,
    *,
    channel: int,
    requested_start: int,
    requested_stop: int,
    identity: InstrumentIdentity,
    captured_at: datetime,
) -> Waveform:
    """Scale the deliberately narrow NORM/BYTE/START=1 DS1102Z-E slice."""

    if preamble.format is not WaveformFormat.BYTE:
        raise WaveformMetadataError("Only BYTE waveform format is supported")
    if preamble.reading_mode is not WaveformReadingMode.NORMAL:
        raise WaveformMetadataError("Only NORM waveform mode is supported")
    if not math.isclose(preamble.x_reference, 0.0, abs_tol=0.0):
        raise WaveformMetadataError("Only the verified zero X reference is supported")
    if not math.isclose(preamble.y_reference, 127.0, abs_tol=0.0):
        raise WaveformMetadataError("Only the verified BYTE Y reference is supported")
    if requested_start != 1:
        raise WaveformMetadataError("Only START=1 has verified time-axis semantics")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    requested_points = requested_stop - requested_start + 1
    if requested_points != len(payload) or preamble.points != len(payload):
        raise WaveformLengthMismatchError(
            "Requested, preamble, and payload point counts do not match"
        )

    times = tuple(
        preamble.x_origin + index * preamble.x_increment
        for index in range(len(payload))
    )
    # Convert each byte to Python int before subtraction; this prevents uint8 wrap.
    voltages = tuple(
        (int(sample) - preamble.y_origin - preamble.y_reference) * preamble.y_increment
        for sample in payload
    )
    return Waveform(
        channel=channel,
        point_count=len(payload),
        sample_interval_seconds=preamble.x_increment,
        time_origin_seconds=preamble.x_origin,
        time_reference=preamble.x_reference,
        voltage_increment=preamble.y_increment,
        voltage_origin=preamble.y_origin,
        voltage_reference=preamble.y_reference,
        time_values=times,
        voltage_values=voltages,
        acquisition_mode=WaveformAcquisitionMode.NORMAL,
        instrument_identity=identity,
        captured_at=captured_at,
        average_count=preamble.count,
        requested_start=requested_start,
        requested_stop=requested_stop,
    )
