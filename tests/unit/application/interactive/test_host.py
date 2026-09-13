from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    FrontendKind,
    FrontendConnectionError,
    OperationBudget,
    SemanticOperation,
    StaleWorkflowRevisionError,
    WorkflowState,
    HostState,
)
from ai_instrument_assistant.adapters.eda.in_memory import InMemoryEDAAdapter
from tests.support.interactive_fakes import FakeDecisionAuthorities, FakeRuntimeLifecycle


NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


class ApplicationHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.issuer = FakeDecisionAuthorities()
        self.host = ApplicationHost(
            design_selection_issuer=self.issuer,
            operation_authorization_issuer=self.issuer,
            physical_confirmation_issuer=self.issuer,
            clock=lambda: NOW,
        )

    def test_one_authoritative_application_session_and_workflow_creation(self) -> None:
        self.assertIs(self.host.application_session, self.host.application_session)
        workflow = self.host.start_workflow("inspect PWM_OUT", "request-1")
        self.assertEqual(workflow.revision, 0)
        self.assertEqual(workflow.state, WorkflowState.IDLE)
        self.assertEqual(self.host.get_workflow(workflow.workflow_id), workflow)

    def test_transition_revision_is_monotonic_and_cas_conflict_is_rejected(self) -> None:
        workflow = self.host.start_workflow("inspect PWM_OUT", "request-1")
        updated = self.host.transition(
            workflow.workflow_id, expected_revision=0, target=WorkflowState.OBSERVING_DESIGN
        )
        self.assertEqual(updated.revision, 1)
        with self.assertRaises(StaleWorkflowRevisionError):
            self.host.transition(
                workflow.workflow_id, expected_revision=0, target=WorkflowState.OBSERVING_DESIGN
            )

    def test_conflicting_frontends_cannot_merge_stale_transitions(self) -> None:
        workflow = self.host.start_workflow("inspect PWM_OUT", "request-1")
        self.host.connect_frontend(FrontendKind.HARNESS, "harness-token")
        self.host.connect_frontend(FrontendKind.JLCEDA, "jlceda-token")
        self.host.transition(workflow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        with self.assertRaises(StaleWorkflowRevisionError):
            self.host.transition(workflow.workflow_id, 0, WorkflowState.CANCELLED)

    def test_operation_plan_is_bounded_and_revisioned(self) -> None:
        workflow = self.host.start_workflow("measure PWM_OUT", "request-1")
        workflow = self.host.transition(workflow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        workflow = self.host.transition(workflow.workflow_id, 1, WorkflowState.DESIGN_CONTEXT_READY)
        workflow = self.host.transition(workflow.workflow_id, 2, WorkflowState.TARGET_RESOLVED)
        updated = self.host.prepare_measurement_plan(
            workflow.workflow_id,
            expected_revision=3,
            probe_target_identity="target:pwm-out",
            operations=(SemanticOperation.GET_STATUS, SemanticOperation.MEASURE_PWM),
            channel=1,
            budgets=(
                OperationBudget(SemanticOperation.GET_STATUS, 1),
                OperationBudget(SemanticOperation.MEASURE_PWM, 1),
            ),
        )
        self.assertEqual(updated.state, WorkflowState.OPERATION_PREPARED)
        self.assertEqual(updated.revision, 4)
        self.assertIsNotNone(updated.operation_plan)

    def test_new_design_observation_invalidates_dependent_ephemeral_state(self) -> None:
        flow = self.host.start_workflow("inspect", "request")
        flow = self.host.transition(flow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        observed = self.host.record_design_observation(
            flow.workflow_id,
            flow.revision,
            "sha256:" + "a" * 64,
            selection_context=InMemoryEDAAdapter.for_pwm_out_scenario().selection_context,
            candidate_binding=None,
            probe_target=None,
        )
        self.assertEqual(observed.state, WorkflowState.DESIGN_CONTEXT_READY)
        self.assertIsNone(observed.trusted_design_decision_ref)
        self.assertIsNone(observed.operation_scope_ref)
        self.assertIsNone(observed.physical_confirmation_ref)

    def test_audit_is_bounded_correlated_and_excludes_frontend_principal(self) -> None:
        connection = self.host.connect_frontend(
            FrontendKind.HARNESS, "secret-looking-principal-not-for-audit"
        )
        workflow = self.host.start_workflow("inspect", "request-correlation-1")
        self.host.transition(
            workflow.workflow_id, workflow.revision, WorkflowState.OBSERVING_DESIGN
        )
        self.host.disconnect_frontend(connection.connection_id)
        records = self.host.audit_records
        self.assertTrue(any(item.correlation_id == "request-correlation-1" for item in records))
        self.assertTrue(any(item.action == "workflow_transition:observing_design" for item in records))
        self.assertTrue(all(len(item.action) <= 128 for item in records))
        self.assertNotIn("secret-looking-principal-not-for-audit", repr(records))


class ApplicationHostLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_owns_shutdown_and_invalidates_ephemeral_frontend_state(self) -> None:
        lifecycle = FakeRuntimeLifecycle()
        host = ApplicationHost(
            design_selection_issuer=FakeDecisionAuthorities(),
            clock=lambda: NOW,
            runtime_lifecycle=lifecycle,
        )
        connection = host.connect_frontend(FrontendKind.HARNESS, "token")
        await host.shutdown()
        await host.shutdown()
        self.assertEqual(host.application_session.host_state, HostState.STOPPED)
        self.assertEqual(lifecycle.shutdown_calls, 1)
        with self.assertRaises(FrontendConnectionError):
            host.get_connection(connection.connection_id)


if __name__ == "__main__":
    unittest.main()
