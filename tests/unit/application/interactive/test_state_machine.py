from __future__ import annotations

import unittest

from ai_instrument_assistant.application.interactive import (
    IllegalWorkflowTransitionError,
    WorkflowState,
    transition_allowed,
)


class WorkflowStateMachineTests(unittest.TestCase):
    def test_representative_legal_transitions(self) -> None:
        self.assertTrue(transition_allowed(WorkflowState.IDLE, WorkflowState.OBSERVING_DESIGN))
        self.assertTrue(transition_allowed(WorkflowState.WAITING_FOR_DESIGN_SELECTION, WorkflowState.TARGET_RESOLVED))
        self.assertTrue(transition_allowed(WorkflowState.READY_TO_EXECUTE, WorkflowState.CONNECTING_INSTRUMENT))

    def test_illegal_jump_fails_closed(self) -> None:
        with self.assertRaises(IllegalWorkflowTransitionError):
            transition_allowed(
                WorkflowState.WAITING_FOR_PHYSICAL_CONFIRMATION,
                WorkflowState.COMPLETE,
                raise_on_error=True,
            )

    def test_every_nonterminal_state_can_cancel_or_fail(self) -> None:
        for state in WorkflowState:
            if state in {WorkflowState.COMPLETE, WorkflowState.FAILED, WorkflowState.CANCELLED}:
                continue
            with self.subTest(state=state):
                self.assertTrue(transition_allowed(state, WorkflowState.CANCELLED))
                self.assertTrue(transition_allowed(state, WorkflowState.FAILED))


if __name__ == "__main__":
    unittest.main()
