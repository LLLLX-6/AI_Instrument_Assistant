from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    FrontendKind,
    OperationBudget,
    SemanticOperation,
    WorkflowState,
)
from ai_instrument_assistant.integrations.interactive import InteractiveWireProjector
from tests.support.interactive_fakes import (
    FakeDecisionAuthorities,
    synthetic_ambiguous_binding,
)


class InteractiveWireProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        authorities = FakeDecisionAuthorities()
        self.host = ApplicationHost(
            design_selection_issuer=authorities,
            operation_authorization_issuer=authorities,
            physical_confirmation_issuer=authorities,
        )
        self.connection = self.host.connect_frontend(FrontendKind.JLCEDA, "fake:jlceda")
        self.projector = InteractiveWireProjector(self.host)

    def test_snapshot_is_schema_bounded_and_contains_no_authority_objects(self) -> None:
        workflow = self.host.start_workflow("PWM_OUT", "request:1")
        batch = self.host.subscribe(self.connection.connection_id, 0)
        message = self.projector.snapshot_event(self.connection, batch.snapshot)
        self.assertEqual(message["message_type"], "event")
        self.assertEqual(message["event_type"], "workflow_snapshot")
        self.assertNotIn("trusted_operation_scope", repr(message).lower())
        self.assertNotIn("probe_setup_confirmation", repr(message).lower())
        self.assertEqual(message["payload"]["snapshot"]["workflows"][0]["workflow_id"], str(workflow.workflow_id))
        self.projector.validate(message)

    def test_challenge_projection_preserves_exact_binding(self) -> None:
        workflow = self.host.start_workflow("PWM_OUT", "request:1")
        workflow = self.host.transition(workflow.workflow_id, 0, WorkflowState.OBSERVING_DESIGN)
        context, typed_binding, tokens = synthetic_ambiguous_binding()
        workflow = self.host.record_design_observation(
            workflow.workflow_id,
            workflow.revision,
            "sha256:" + "a" * 64,
            selection_context=context,
            candidate_binding=typed_binding,
            probe_target=None,
        )
        challenge = self.host.request_design_selection(
            workflow.workflow_id, workflow.revision,
            FrontendKind.JLCEDA,
            timedelta(minutes=2),
        )
        event = next(item for item in self.host.subscribe(self.connection.connection_id, 0).events if item.payload.challenge == challenge)
        message = self.projector.event(self.connection, event)
        binding = message["payload"]["challenge"]["binding"]
        self.assertEqual(
            binding["allowed_candidate_identities"],
            [token for token, _identity in tokens],
        )
        self.projector.validate(message)


if __name__ == "__main__":
    unittest.main()
