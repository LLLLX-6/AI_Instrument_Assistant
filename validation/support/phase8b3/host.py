from __future__ import annotations

import asyncio
import string
import sys
from collections.abc import Awaitable, Callable

from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    DesignSelectionCandidateIdentity,
    DesignSelectionCandidateSetBinding,
)

from .coordinator import (
    ConfirmationAction,
    OperationAuthorizationAction,
    Phase8B3OperationAuthorizationPrompt,
    Phase8B3ProbeConfirmationPrompt,
)


class BoundedCliHostInteraction:
    """Exact menu actions are trusted Host events; labels are display-only."""

    def __init__(
        self,
        read_action: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self._read_action = read_action or _console_action

    async def choose_design_candidate(
        self, binding: DesignSelectionCandidateSetBinding
    ) -> DesignSelectionCandidateIdentity | None:
        if len(binding.candidate_identities) > len(string.ascii_uppercase):
            return None
        print("Choose the exact observed design object (X cancels):", file=sys.stderr)
        choices: dict[str, DesignSelectionCandidateIdentity] = {}
        for index, (candidate, identity) in enumerate(
            zip(binding.presented_candidates, binding.candidate_identities, strict=True)
        ):
            key = string.ascii_uppercase[index]
            choices[key] = identity
            kind = candidate.provider_kind or candidate.object_type.value
            label = candidate.display_name or "unavailable"
            print(f"  {key}. {kind} — {label}", file=sys.stderr)
        action = (await self._read_action("Selection [A.. / X]: ")).strip().upper()
        return None if action == "X" else choices.get(action)

    async def confirm_probe_connection(
        self, prompt: Phase8B3ProbeConfirmationPrompt
    ) -> ConfirmationAction:
        print(
            f"Target: {prompt.display_label}; CH{prompt.channel}; maximum expected "
            f"{prompt.maximum_expected_voltage_v:g} V.",
            file=sys.stderr,
        )
        print(prompt.safe_low_voltage_statement, file=sys.stderr)
        print(prompt.common_ground_statement, file=sys.stderr)
        print(prompt.wiring_statement, file=sys.stderr)
        action = (await self._read_action("Confirm all statements [C / X]: ")).strip().upper()
        return ConfirmationAction.CONFIRM if action == "C" else ConfirmationAction.CANCEL

    async def authorize_operation_plan(
        self, prompt: Phase8B3OperationAuthorizationPrompt
    ) -> OperationAuthorizationAction:
        print("Authorize this run only:", file=sys.stderr)
        print(
            f"- {prompt.status_operation} once; - {prompt.pwm_operation} once on "
            f"CH{prompt.pwm_channel}; - no other operation and no retry.",
            file=sys.stderr,
        )
        action = (await self._read_action("Authorize exact plan [O / X]: ")).strip().upper()
        return (
            OperationAuthorizationAction.AUTHORIZE
            if action == "O"
            else OperationAuthorizationAction.CANCEL
        )


async def _console_action(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)
