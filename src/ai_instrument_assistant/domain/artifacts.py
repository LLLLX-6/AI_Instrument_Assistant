from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .errors import DomainInvariantError


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    """Provider-neutral reference to evidence stored outside a tool response."""

    artifact_id: UUID
    uri: str
    media_type: str
    size_bytes: int | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, UUID):
            raise DomainInvariantError("artifact_id must be a UUID")
        object.__setattr__(self, "uri", _text(self.uri, "uri"))
        object.__setattr__(self, "media_type", _text(self.media_type, "media_type"))
        if ":" not in self.uri:
            raise DomainInvariantError("uri must include a scheme")
        if "/" not in self.media_type:
            raise DomainInvariantError("media_type must be a MIME type")
        if self.size_bytes is not None and (
            isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or self.size_bytes < 0
        ):
            raise DomainInvariantError("size_bytes must be a non-negative integer")
        if self.sha256 is not None:
            if not isinstance(self.sha256, str):
                raise DomainInvariantError("sha256 must be a hexadecimal string")
            normalized = self.sha256.lower()
            if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
                raise DomainInvariantError("sha256 must contain 64 hexadecimal characters")
            object.__setattr__(self, "sha256", normalized)


@dataclass(frozen=True, slots=True)
class WaveformArtifact:
    """Bounded waveform metadata; sample arrays remain in an ArtifactStore."""

    reference: ArtifactReference
    channel: int
    point_count: int
    sample_interval_seconds: float
    time_start_seconds: float
    time_end_seconds: float
    minimum_voltage: float
    maximum_voltage: float
    acquisition_mode: str
    captured_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ArtifactReference):
            raise DomainInvariantError("reference must be an ArtifactReference")
        if isinstance(self.channel, bool) or self.channel not in (1, 2):
            raise DomainInvariantError("waveform artifact channel must be 1 or 2")
        if isinstance(self.point_count, bool) or not isinstance(self.point_count, int) or self.point_count < 1:
            raise DomainInvariantError("point_count must be a positive integer")
        for field_name in (
            "sample_interval_seconds", "time_start_seconds", "time_end_seconds",
            "minimum_voltage", "maximum_voltage",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise DomainInvariantError(f"{field_name} must be finite")
        if self.sample_interval_seconds <= 0:
            raise DomainInvariantError("sample_interval_seconds must be positive")
        if self.time_end_seconds < self.time_start_seconds:
            raise DomainInvariantError("waveform artifact time range is invalid")
        if self.maximum_voltage < self.minimum_voltage:
            raise DomainInvariantError("waveform artifact voltage range is invalid")
        object.__setattr__(self, "acquisition_mode", _text(self.acquisition_mode, "acquisition_mode"))
        if not isinstance(self.captured_at, datetime) or self.captured_at.utcoffset() is None:
            raise DomainInvariantError("captured_at must be timezone-aware")


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainInvariantError(f"{field_name} must be non-empty text")
    return value.strip()
