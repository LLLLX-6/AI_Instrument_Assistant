from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import DomainInvariantError


@dataclass(frozen=True, slots=True, init=False)
class DutyCycle:
    """Unit-explicit duty cycle with ratio as its canonical representation."""

    _ratio: float

    def __init__(self) -> None:
        raise TypeError("Use DutyCycle.from_ratio() or DutyCycle.from_percent()")

    @classmethod
    def from_ratio(cls, ratio: float) -> DutyCycle:
        normalized = _finite_number(ratio, "duty cycle ratio")
        if not 0.0 <= normalized <= 1.0:
            raise DomainInvariantError(
                "duty cycle ratio must be between 0.0 and 1.0 inclusive"
            )
        instance = object.__new__(cls)
        object.__setattr__(instance, "_ratio", normalized)
        return instance

    @classmethod
    def from_percent(cls, percent: float) -> DutyCycle:
        normalized = _finite_number(percent, "duty cycle percent")
        if not 0.0 <= normalized <= 100.0:
            raise DomainInvariantError(
                "duty cycle percent must be between 0.0 and 100.0 inclusive"
            )
        return cls.from_ratio(normalized / 100.0)

    @property
    def ratio(self) -> float:
        return self._ratio

    @property
    def percent(self) -> float:
        return self._ratio * 100.0


def _finite_number(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainInvariantError(f"{field_name} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise DomainInvariantError(f"{field_name} must be finite")
    return normalized
