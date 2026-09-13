from __future__ import annotations

import asyncio
import unittest

from ai_instrument_assistant.adapters.eda.in_memory import InMemoryEDAAdapter
from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    WorkflowState,
)
from ai_instrument_assistant.application.ports.eda_interface import (
    EDAConnectionLostError,
    EDACapabilitySet,
    EDAInterface,
    EDANotConnectedError,
    EDARequestTimeoutError,
    HighlightCommand,
    HighlightResult,
)
from ai_instrument_assistant.integrations.interactive.actions import (
    DesignObservationStatus,
    ProductionInteractiveApplicationActions,
)
from tests.support.interactive_fakes import FakeDecisionAuthorities


class DelayedEDA(EDAInterface):
    def __init__(self, delegate: InMemoryEDAAdapter) -> None:
        self.delegate = delegate
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.document_calls = 0
        self.selection_calls = 0
        self.failure: Exception | None = None

    @property
    def capabilities(self) -> EDACapabilitySet:
        return self.delegate.capabilities

    async def get_active_document(self):
        self.document_calls += 1
        self.entered.set()
        await self.release.wait()
        if self.failure is not None:
            raise self.failure
        return await self.delegate.get_active_document()

    async def get_selection(self):
        self.selection_calls += 1
        return await self.delegate.get_selection()

    async def highlight(self, command: HighlightCommand) -> HighlightResult:
        return await self.delegate.highlight(command)


class ProductionInteractiveActionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.host = ApplicationHost(design_selection_issuer=FakeDecisionAuthorities())
        self.flow = self.host.start_workflow("observe PWM_OUT", "request-actions")
        self.flow = self.host.transition(
            self.flow.workflow_id,
            self.flow.revision,
            WorkflowState.OBSERVING_DESIGN,
        )
        self.eda = DelayedEDA(InMemoryEDAAdapter.for_pwm_out_scenario())
        self.actions = ProductionInteractiveApplicationActions(
            host=self.host,
            eda=self.eda,
        )

    async def test_successful_observe_calls_provider_port_once_and_commits(self) -> None:
        task = asyncio.create_task(
            self.actions.request_design_observation(
                self.flow.workflow_id,
                self.flow.revision,
            )
        )
        await self.eda.entered.wait()
        self.eda.release.set()
        result = await task

        self.assertEqual(result.status, DesignObservationStatus.COMMITTED)
        self.assertEqual(self.eda.document_calls, 1)
        self.assertEqual(self.eda.selection_calls, 1)
        updated = self.host.get_workflow(self.flow.workflow_id)
        self.assertEqual(updated.state, WorkflowState.TARGET_RESOLVED)
        self.assertTrue(updated.design_observation_ref.startswith("sha256:"))
        self.assertIsNotNone(updated.probe_target)

    async def test_delayed_result_is_discarded_and_host_lock_is_not_held(self) -> None:
        task = asyncio.create_task(
            self.actions.request_design_observation(
                self.flow.workflow_id,
                self.flow.revision,
            )
        )
        await self.eda.entered.wait()

        cancelled = await asyncio.wait_for(
            asyncio.to_thread(
                self.host.cancel_workflow,
                self.flow.workflow_id,
                self.flow.revision,
                "user_cancelled",
            ),
            timeout=0.5,
        )
        self.assertEqual(cancelled.state, WorkflowState.CANCELLED)
        self.eda.release.set()
        result = await task

        self.assertEqual(result.status, DesignObservationStatus.STALE)
        current = self.host.get_workflow(self.flow.workflow_id)
        self.assertEqual(current.state, WorkflowState.CANCELLED)
        self.assertIsNone(current.design_observation_ref)

    async def test_provider_failure_commits_no_observation_and_host_remains_usable(self) -> None:
        self.eda.failure = EDARequestTimeoutError("provider payload must not escape")
        task = asyncio.create_task(
            self.actions.request_design_observation(
                self.flow.workflow_id,
                self.flow.revision,
            )
        )
        await self.eda.entered.wait()
        self.eda.release.set()
        result = await task

        self.assertEqual(result.status, DesignObservationStatus.FAILED)
        self.assertEqual(result.code, "design_observation_unavailable")
        failed = self.host.get_workflow(self.flow.workflow_id)
        self.assertEqual(failed.state, WorkflowState.FAILED)
        self.assertIsNone(failed.design_observation_ref)
        another = self.host.start_workflow("still usable", "request-next")
        self.assertEqual(another.state, WorkflowState.IDLE)

    async def test_unavailable_timeout_and_connection_failure_are_bounded(self) -> None:
        failures = (
            EDANotConnectedError("unavailable raw provider detail"),
            EDARequestTimeoutError("timeout raw provider detail"),
            EDAConnectionLostError("failure raw provider detail"),
        )
        for index, failure in enumerate(failures):
            with self.subTest(failure=type(failure).__name__):
                host = ApplicationHost(design_selection_issuer=FakeDecisionAuthorities())
                flow = host.start_workflow("observe", f"request-{index}")
                flow = host.transition(
                    flow.workflow_id,
                    flow.revision,
                    WorkflowState.OBSERVING_DESIGN,
                )
                eda = DelayedEDA(InMemoryEDAAdapter.for_pwm_out_scenario())
                eda.failure = failure
                action = ProductionInteractiveApplicationActions(host=host, eda=eda)
                task = asyncio.create_task(
                    action.request_design_observation(flow.workflow_id, flow.revision)
                )
                await eda.entered.wait()
                eda.release.set()
                result = await task
                self.assertEqual(result.status, DesignObservationStatus.FAILED)
                self.assertEqual(result.code, "design_observation_unavailable")
                self.assertNotIn("raw provider detail", repr(result))
                self.assertIsNone(host.get_workflow(flow.workflow_id).design_observation_ref)


if __name__ == "__main__":
    unittest.main()
