from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    ChallengeRejectedError,
    FrontendKind,
    InvalidEventCursorError,
    OperationBudget,
    SemanticOperation,
    WorkflowState,
)
from tests.support.interactive_fakes import FakeTrustedDecisionIssuer


NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


class ReconnectAndCancelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.issuer = FakeTrustedDecisionIssuer()
        self.host = ApplicationHost(trusted_issuer=self.issuer, clock=lambda: NOW)

    def test_reconnect_receives_snapshot_before_events_and_grants_no_authority(self) -> None:
        old = self.host.connect_frontend(FrontendKind.HARNESS, "token")
        flow = self.host.start_workflow("inspect", "request")
        self.host.transition(flow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        first = self.host.subscribe(old.connection_id, cursor=0)
        self.assertGreaterEqual(len(first.snapshot.workflows), 1)
        self.assertGreaterEqual(len(first.events), 1)
        self.host.disconnect_frontend(old.connection_id)
        new = self.host.connect_frontend(FrontendKind.HARNESS, "token")
        resumed = self.host.subscribe(new.connection_id, cursor=first.next_cursor)
        self.assertNotEqual(new.connection_id, old.connection_id)
        self.assertGreaterEqual(len(resumed.snapshot.workflows), 1)
        self.assertTrue(
            all(event.event_type.value == "frontend_connection_changed" for event in resumed.events)
        )
        self.assertEqual(resumed.next_cursor, resumed.snapshot.event_cursor)
        current = self.host.get_workflow(flow.workflow_id)
        self.assertIsNone(current.operation_scope_ref)
        self.assertIsNone(current.physical_confirmation_ref)

    def test_invalid_future_or_negative_cursor_fails_closed(self) -> None:
        connection = self.host.connect_frontend(FrontendKind.HARNESS, "token")
        for cursor in (-1, 999):
            with self.subTest(cursor=cursor):
                with self.assertRaises(InvalidEventCursorError):
                    self.host.subscribe(connection.connection_id, cursor)

    def test_cursor_older_than_retained_event_window_fails_closed(self) -> None:
        host = ApplicationHost(
            trusted_issuer=self.issuer,
            clock=lambda: NOW,
            event_retention=2,
        )
        connection = host.connect_frontend(FrontendKind.HARNESS, "token")
        host.start_workflow("one", "request-1")
        host.start_workflow("two", "request-2")
        with self.assertRaises(InvalidEventCursorError):
            host.subscribe(connection.connection_id, cursor=0)
        current = host.subscribe(connection.connection_id, cursor=1)
        self.assertEqual([event.cursor for event in current.events], [2, 3])

    def test_cancel_waiting_challenge_withdraws_it_and_has_zero_side_effects(self) -> None:
        connection = self.host.connect_frontend(FrontendKind.JLCEDA, "token")
        flow = self.host.start_workflow("inspect", "request")
        flow = self.host.transition(flow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        flow = self.host.transition(flow.workflow_id, 1, WorkflowState.DESIGN_CONTEXT_READY)
        challenge = self.host.request_design_selection(
            flow.workflow_id, 2, "sha256:" + "a" * 64, "sha256:" + "b" * 64,
            ("candidate:a", "candidate:b"), FrontendKind.JLCEDA,
            timedelta(minutes=5),
        )
        cancelled = self.host.cancel_workflow(
            flow.workflow_id, challenge.workflow_revision, "user_cancelled"
        )
        self.assertEqual(cancelled.state, WorkflowState.CANCELLED)
        self.assertEqual(cancelled.pending_challenge_ids, ())
        self.assertEqual(self.issuer.total_calls, 0)
        self.assertEqual(self.host.execution_dispatch_count, 0)
        with self.assertRaises(ChallengeRejectedError):
            self.host.answer_design_selection(
                connection.connection_id, challenge.workflow_id,
                challenge.workflow_revision, challenge.challenge_id, challenge.nonce,
                challenge.binding.candidate_set_identity, "candidate:a",
            )

    def test_cancel_waiting_authorization_or_confirmation_never_dispatches(self) -> None:
        jlceda = self.host.connect_frontend(FrontendKind.JLCEDA, "jlceda")
        harness = self.host.connect_frontend(FrontendKind.HARNESS, "harness")
        flow = self.host.start_workflow("measure", "request")
        flow = self.host.transition(flow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        flow = self.host.transition(flow.workflow_id, 1, WorkflowState.DESIGN_CONTEXT_READY)
        selection = self.host.request_design_selection(
            flow.workflow_id, 2, "sha256:" + "a" * 64, "sha256:" + "b" * 64,
            ("candidate:a", "candidate:b"), FrontendKind.JLCEDA, timedelta(minutes=5),
        )
        flow = self.host.answer_design_selection(
            jlceda.connection_id, selection.workflow_id, selection.workflow_revision,
            selection.challenge_id, selection.nonce, selection.binding.candidate_set_identity,
            "candidate:a",
        )
        flow = self.host.prepare_measurement_plan(
            flow.workflow_id, flow.revision, flow.probe_target_ref,
            (SemanticOperation.MEASURE_PWM,), 1,
            (OperationBudget(SemanticOperation.MEASURE_PWM, 1),),
        )
        authorization = self.host.request_operation_authorization(
            flow.workflow_id, flow.revision, FrontendKind.HARNESS, timedelta(minutes=5)
        )
        cancelled = self.host.cancel_workflow(
            flow.workflow_id, authorization.workflow_revision, "user_cancelled"
        )
        self.assertEqual(cancelled.state, WorkflowState.CANCELLED)
        self.assertEqual(self.issuer.operation_calls, 0)
        self.assertEqual(self.host.execution_dispatch_count, 0)

        flow = self.host.start_workflow("measure-2", "request-2")
        flow = self.host.transition(flow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        flow = self.host.transition(flow.workflow_id, 1, WorkflowState.DESIGN_CONTEXT_READY)
        selection = self.host.request_design_selection(
            flow.workflow_id, 2, "sha256:" + "c" * 64, "sha256:" + "d" * 64,
            ("candidate:c", "candidate:d"), FrontendKind.JLCEDA, timedelta(minutes=5),
        )
        flow = self.host.answer_design_selection(
            jlceda.connection_id, selection.workflow_id, selection.workflow_revision,
            selection.challenge_id, selection.nonce, selection.binding.candidate_set_identity,
            "candidate:c",
        )
        flow = self.host.prepare_measurement_plan(
            flow.workflow_id, flow.revision, flow.probe_target_ref,
            (SemanticOperation.MEASURE_PWM,), 1,
            (OperationBudget(SemanticOperation.MEASURE_PWM, 1),),
        )
        authorization = self.host.request_operation_authorization(
            flow.workflow_id, flow.revision, FrontendKind.HARNESS, timedelta(minutes=5)
        )
        flow = self.host.answer_operation_authorization(
            harness.connection_id, authorization.workflow_id,
            authorization.workflow_revision, authorization.challenge_id,
            authorization.nonce, authorization.binding.operation_plan_identity, True,
        )
        physical = self.host.request_physical_setup(
            flow.workflow_id, flow.revision, FrontendKind.JLCEDA, 3.3,
            timedelta(minutes=5),
        )
        cancelled = self.host.cancel_workflow(
            flow.workflow_id, physical.workflow_revision, "user_cancelled"
        )
        self.assertEqual(cancelled.state, WorkflowState.CANCELLED)
        self.assertEqual(self.issuer.physical_calls, 0)
        self.assertEqual(self.host.execution_dispatch_count, 0)


if __name__ == "__main__":
    unittest.main()
