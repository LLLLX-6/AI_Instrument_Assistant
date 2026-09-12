from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    ChallengeRejectedError,
    FrontendKind,
    OperationBudget,
    SemanticOperation,
    WorkflowState,
)
from tests.support.interactive_fakes import FakeTrustedDecisionIssuer


NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


class ChallengeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = NOW
        self.issuer = FakeTrustedDecisionIssuer()
        self.host = ApplicationHost(trusted_issuer=self.issuer, clock=lambda: self.now)
        self.jlceda = self.host.connect_frontend(FrontendKind.JLCEDA, "jlceda-token")
        self.harness = self.host.connect_frontend(FrontendKind.HARNESS, "harness-token")

    def _selection_challenge(self):
        flow = self.host.start_workflow("inspect PWM_OUT", "request-1")
        flow = self.host.transition(flow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        flow = self.host.transition(flow.workflow_id, 1, WorkflowState.DESIGN_CONTEXT_READY)
        return self.host.request_design_selection(
            flow.workflow_id,
            expected_revision=2,
            observation_identity="sha256:" + "a" * 64,
            candidate_set_identity="sha256:" + "b" * 64,
            candidate_identities=("candidate:wire-pwm-out", "candidate:component-u1"),
            allowed_frontend=FrontendKind.JLCEDA,
            ttl=timedelta(minutes=5),
        )

    def test_valid_answer_is_consumed_once_and_calls_trusted_issuer(self) -> None:
        challenge = self._selection_challenge()
        result = self.host.answer_design_selection(
            connection_id=self.jlceda.connection_id,
            workflow_id=challenge.workflow_id,
            expected_revision=challenge.workflow_revision,
            challenge_id=challenge.challenge_id,
            nonce=challenge.nonce,
            candidate_set_identity=challenge.binding.candidate_set_identity,
            candidate_identity="candidate:wire-pwm-out",
        )
        self.assertEqual(result.state, WorkflowState.TARGET_RESOLVED)
        self.assertEqual(self.issuer.design_calls, 1)
        with self.assertRaises(ChallengeRejectedError):
            self.host.answer_design_selection(
                connection_id=self.jlceda.connection_id,
                workflow_id=challenge.workflow_id,
                expected_revision=challenge.workflow_revision,
                challenge_id=challenge.challenge_id,
                nonce=challenge.nonce,
                candidate_set_identity=challenge.binding.candidate_set_identity,
                candidate_identity="candidate:wire-pwm-out",
            )
        self.assertEqual(self.issuer.design_calls, 1)

    def test_wrong_frontend_generation_workflow_revision_candidate_and_nonce_fail(self) -> None:
        mutations = (
            {"connection_id": self.harness.connection_id},
            {"workflow_id": "wrong-workflow"},
            {"expected_revision": 999},
            {"candidate_set_identity": "sha256:" + "c" * 64},
            {"candidate_identity": "candidate:missing"},
            {"nonce": "wrong-nonce-value-aaaaaaaa"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                challenge = self._selection_challenge()
                values = dict(
                    connection_id=self.jlceda.connection_id,
                    workflow_id=challenge.workflow_id,
                    expected_revision=challenge.workflow_revision,
                    challenge_id=challenge.challenge_id,
                    nonce=challenge.nonce,
                    candidate_set_identity=challenge.binding.candidate_set_identity,
                    candidate_identity="candidate:wire-pwm-out",
                )
                values.update(mutation)
                with self.assertRaises(ChallengeRejectedError):
                    self.host.answer_design_selection(**values)
        self.assertEqual(self.issuer.design_calls, 0)

    def test_expired_challenge_and_old_application_generation_fail(self) -> None:
        challenge = self._selection_challenge()
        self.now = NOW + timedelta(minutes=6)
        with self.assertRaises(ChallengeRejectedError):
            self.host.answer_design_selection(
                connection_id=self.jlceda.connection_id,
                workflow_id=challenge.workflow_id,
                expected_revision=challenge.workflow_revision,
                challenge_id=challenge.challenge_id,
                nonce=challenge.nonce,
                candidate_set_identity=challenge.binding.candidate_set_identity,
                candidate_identity="candidate:wire-pwm-out",
            )
        restarted = ApplicationHost(trusted_issuer=self.issuer, clock=lambda: self.now)
        with self.assertRaises(ChallengeRejectedError):
            restarted.answer_design_selection(
                connection_id=self.jlceda.connection_id,
                workflow_id=challenge.workflow_id,
                expected_revision=challenge.workflow_revision,
                challenge_id=challenge.challenge_id,
                nonce=challenge.nonce,
                candidate_set_identity=challenge.binding.candidate_set_identity,
                candidate_identity="candidate:wire-pwm-out",
            )

    def test_changed_operation_plan_channel_and_target_invalidate_physical_confirmation(self) -> None:
        challenge = self._selection_challenge()
        flow = self.host.answer_design_selection(
            self.jlceda.connection_id, challenge.workflow_id,
            challenge.workflow_revision, challenge.challenge_id, challenge.nonce,
            challenge.binding.candidate_set_identity, "candidate:wire-pwm-out",
        )
        flow = self.host.prepare_measurement_plan(
            flow.workflow_id, flow.revision, "target:pwm-out",
            (SemanticOperation.MEASURE_PWM,), 1,
            (OperationBudget(SemanticOperation.MEASURE_PWM, 1),),
        )
        auth = self.host.request_operation_authorization(
            flow.workflow_id, flow.revision, FrontendKind.HARNESS, timedelta(minutes=5)
        )
        flow = self.host.answer_operation_authorization(
            self.harness.connection_id, auth.workflow_id, auth.workflow_revision,
            auth.challenge_id, auth.nonce, auth.binding.operation_plan_identity, True,
        )
        physical = self.host.request_physical_setup(
            flow.workflow_id, flow.revision, FrontendKind.JLCEDA, 3.3,
            timedelta(minutes=5),
        )
        self.host.replace_operation_plan(
            flow.workflow_id,
            expected_revision=physical.workflow_revision,
            probe_target_identity="target:pwm-out-v2",
            operations=(SemanticOperation.MEASURE_PWM,),
            channel=2,
            budgets=(OperationBudget(SemanticOperation.MEASURE_PWM, 1),),
        )
        with self.assertRaises(ChallengeRejectedError):
            self.host.answer_physical_setup(
                self.jlceda.connection_id, physical.workflow_id,
                physical.workflow_revision, physical.challenge_id, physical.nonce,
                physical.binding.probe_target_identity,
                physical.binding.operation_plan_identity, physical.binding.channel,
                physical.binding.maximum_expected_voltage_v,
                True, True, True, True,
            )
        self.assertEqual(self.issuer.physical_calls, 0)


if __name__ == "__main__":
    unittest.main()
