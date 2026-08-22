from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class FixtureFormatError(RuntimeError):
    """A shared fixture does not follow the contract fixture wrapper format."""


@dataclass(frozen=True, slots=True)
class FixtureCase:
    path: Path
    expectation: str
    description: str
    schema_ref: str
    instance: Any


class FixtureLoader:
    """Loads shared fixtures without embedding any protocol field definitions."""

    def __init__(self, fixtures_root: Path) -> None:
        self._fixtures_root = fixtures_root.resolve()
        if not self._fixtures_root.is_dir():
            raise FileNotFoundError(
                f"Shared fixture directory does not exist: {self._fixtures_root}"
            )

    @classmethod
    def from_protocol_root(cls, protocol_root: Path) -> FixtureLoader:
        return cls(protocol_root / "fixtures")

    def load(self, expectation: str) -> tuple[FixtureCase, ...]:
        if expectation not in ("valid", "invalid"):
            raise ValueError("Fixture expectation must be 'valid' or 'invalid'")

        expectation_root = self._fixtures_root / expectation
        if not expectation_root.is_dir():
            raise FileNotFoundError(
                f"Shared fixture expectation directory does not exist: {expectation_root}"
            )

        return tuple(
            self._load_case(path, expectation)
            for path in sorted(expectation_root.rglob("*.case.json"))
        )

    def load_all(self) -> tuple[FixtureCase, ...]:
        return self.load("valid") + self.load("invalid")

    @staticmethod
    def _load_case(path: Path, expectation: str) -> FixtureCase:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FixtureFormatError(f"Cannot read shared fixture {path}: {error}") from error

        if not isinstance(document, dict):
            raise FixtureFormatError(f"Fixture root must be an object: {path}")

        description = document.get("description")
        schema_ref = document.get("schema_ref")
        if not isinstance(description, str) or not description:
            raise FixtureFormatError(f"Fixture has no description: {path}")
        if not isinstance(schema_ref, str) or not schema_ref:
            raise FixtureFormatError(f"Fixture has no schema_ref: {path}")
        if "instance" not in document:
            raise FixtureFormatError(f"Fixture has no instance: {path}")

        return FixtureCase(
            path=path.resolve(),
            expectation=expectation,
            description=description,
            schema_ref=schema_ref,
            instance=document["instance"],
        )
