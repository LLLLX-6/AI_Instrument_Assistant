"""Provider-neutral business domain."""

from .errors import DomainInvariantError
from .values import DutyCycle

__all__ = ["DomainInvariantError", "DutyCycle"]
