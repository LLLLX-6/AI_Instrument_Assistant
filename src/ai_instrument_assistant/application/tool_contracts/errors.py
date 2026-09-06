from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContractIssue:
    """Bounded validation detail safe to expose at a tool boundary."""

    path: str
    rule: str


class ToolContractValidationError(ValueError):
    """A request or response failed its JSON Schema contract."""

    def __init__(self, issues: tuple[ContractIssue, ...]) -> None:
        self.issues = issues
        super().__init__("tool payload does not satisfy its contract")
