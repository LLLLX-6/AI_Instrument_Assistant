from __future__ import annotations

from dataclasses import dataclass


def _finite_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > 256 or any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{field} must be bounded printable text")
    return normalized


@dataclass(frozen=True, slots=True)
class InstrumentIdentity:
    manufacturer: str
    model: str
    serial_number: str
    firmware_version: str
    raw_identity: str | None = None

    def __post_init__(self) -> None:
        for field in ("manufacturer", "model", "serial_number", "firmware_version"):
            object.__setattr__(self, field, _finite_text(getattr(self, field), field))
        if self.raw_identity is not None:
            object.__setattr__(
                self,
                "raw_identity",
                _finite_text(self.raw_identity, "raw_identity"),
            )
