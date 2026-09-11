from __future__ import annotations

import unittest

from tests.unit.validation.test_phase8b3_coordinator import ambiguous_projection
from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    build_candidate_set_binding,
)
from validation.support.phase8b3.coordinator import (
    ConfirmationAction,
    OperationAuthorizationAction,
    Phase8B3OperationAuthorizationPrompt,
    Phase8B3ProbeConfirmationPrompt,
)
from validation.support.phase8b3.host import BoundedCliHostInteraction


class Phase8B3BoundedCliHostTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_menu_key_selects_identity_not_display_name(self):
        projection = await ambiguous_projection()
        binding = build_candidate_set_binding(
            selection_context=projection.design_context.selection,
            selection_observed_at=projection.design_context.evidence[0].observed_at,
        )
        host = BoundedCliHostInteraction(lambda _: _value("A"))
        selected = await host.choose_design_candidate(binding)
        self.assertEqual(selected, binding.candidate_identities[0])

        rejected = BoundedCliHostInteraction(lambda _: _value("PWM_OUT"))
        self.assertIsNone(await rejected.choose_design_candidate(binding))

    async def test_only_exact_c_action_confirms_all_displayed_statements(self):
        prompt = Phase8B3ProbeConfirmationPrompt(
            workflow_id="workflow",
            request_correlation_id="request",
            probe_target_id=__import__("uuid").UUID("11111111-1111-4111-8111-111111111111"),
            target_ref="net:pwm-out",
            display_label="PWM_OUT",
        )
        confirmed = BoundedCliHostInteraction(lambda _: _value("C"))
        self.assertIs(await confirmed.confirm_probe_connection(prompt), ConfirmationAction.CONFIRM)
        for value in ("yes", "confirm", "", "X"):
            with self.subTest(value=value):
                rejected = BoundedCliHostInteraction(lambda _, value=value: _value(value))
                self.assertIs(await rejected.confirm_probe_connection(prompt), ConfirmationAction.CANCEL)

    async def test_only_exact_o_action_authorizes_the_two_fixed_scopes(self):
        prompt = Phase8B3OperationAuthorizationPrompt("workflow", "request")
        approved = BoundedCliHostInteraction(lambda _: _value("O"))
        self.assertIs(
            await approved.authorize_operation_plan(prompt),
            OperationAuthorizationAction.AUTHORIZE,
        )
        self.assertEqual((prompt.status_operation, prompt.status_budget), ("hardware.get_status", 1))
        self.assertEqual((prompt.pwm_operation, prompt.pwm_channel, prompt.pwm_budget), ("hardware.measure_pwm", 1, 1))
        for value in ("yes", "authorize", "C", "X"):
            denied = BoundedCliHostInteraction(lambda _, value=value: _value(value))
            self.assertIs(
                await denied.authorize_operation_plan(prompt),
                OperationAuthorizationAction.CANCEL,
            )


async def _value(value):
    return value


if __name__ == "__main__":
    unittest.main()
