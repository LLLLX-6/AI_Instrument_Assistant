from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

from ai_instrument_assistant.adapters.eda.in_memory import InMemoryEDAAdapter
from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    FrontendKind,
    ValidatedDesignSelectionRequest,
    WorkflowState,
)
from ai_instrument_assistant.application.services import design_selection_disambiguation
from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    DesignSelectionCandidateIdentity,
    TrustedDesignSelectionResolutionStatus,
    build_candidate_set_binding,
    candidate_choice_tokens,
)
from ai_instrument_assistant.domain.eda import (
    DesignObjectKind,
    DesignObjectRef,
    DesignSelection,
    SelectionContext,
)
from ai_instrument_assistant.integrations.interactive.design_selection_issuer import (
    ProductionDesignSelectionDecisionIssuer,
)


NOW = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)


def ambiguous_context() -> SelectionContext:
    source = InMemoryEDAAdapter.for_pwm_out_scenario().selection_context
    document = source.selection.document_ref
    component = DesignObjectRef(
        provider=document.provider,
        object_type=DesignObjectKind.COMPONENT,
        document_id=document.document_id,
        snapshot_id=document.snapshot_id,
        native_id="component-u1",
        canonical_id="jlceda-pro:project-stm32-test:doc-main-schematic:component:u1",
        display_name="U1",
        provider_kind="component",
    )
    return SelectionContext(
        selection=DesignSelection(
            document_ref=document,
            selected_objects=(source.selection.selected_objects[0], component),
            primary_object=None,
        ),
        nets=source.nets,
    )


def changed_ambiguous_context(context: SelectionContext) -> SelectionContext:
    changed = replace(
        context.selection.selected_objects[1],
        native_id="component-u2",
        canonical_id="jlceda-pro:project-stm32-test:doc-main-schematic:component:u2",
        display_name="U2",
    )
    return SelectionContext(
        selection=DesignSelection(
            document_ref=context.selection.document_ref,
            selected_objects=(context.selection.selected_objects[0], changed),
            primary_object=None,
        ),
        nets=context.nets,
    )


class ProductionDesignSelectionIssuerTests(unittest.TestCase):
    def test_delegates_to_existing_factory_and_derives_probe_target(self) -> None:
        context = ambiguous_context()
        binding = build_candidate_set_binding(
            selection_context=context,
            selection_observed_at=NOW,
        )
        issuer = ProductionDesignSelectionDecisionIssuer()
        request = ValidatedDesignSelectionRequest(
            workflow_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            request_correlation_id="request-production-selection",
            selection_context=context,
            candidate_binding=binding,
            selected_candidate=DesignSelectionCandidateIdentity.from_ref(
                context.selection.selected_objects[0]
            ),
            decided_at=NOW + timedelta(seconds=1),
        )

        original = design_selection_disambiguation.issue_trusted_design_selection_decision
        with patch.object(
            design_selection_disambiguation,
            "issue_trusted_design_selection_decision",
            wraps=original,
        ) as delegated:
            resolution = issuer.issue_design_selection(request)

        self.assertEqual(delegated.call_count, 1)
        self.assertEqual(
            resolution.status,
            TrustedDesignSelectionResolutionStatus.RESOLVED,
        )
        self.assertEqual(resolution.chosen_candidate, context.selection.selected_objects[0])
        self.assertEqual(resolution.probe_target.design_object, context.nets[0].ref)

    def test_host_preserves_typed_binding_and_invokes_production_issuer_once(self) -> None:
        issuer = ProductionDesignSelectionDecisionIssuer()
        host = ApplicationHost(design_selection_issuer=issuer, clock=lambda: NOW)
        context = ambiguous_context()
        binding = build_candidate_set_binding(
            selection_context=context,
            selection_observed_at=NOW,
        )
        flow = host.start_workflow("resolve PWM_OUT", "request-production-selection")
        flow = host.transition(flow.workflow_id, flow.revision, WorkflowState.OBSERVING_DESIGN)
        flow = host.record_design_observation(
            flow.workflow_id,
            flow.revision,
            "sha256:" + "a" * 64,
            selection_context=context,
            candidate_binding=binding,
            probe_target=None,
        )
        self.assertIs(flow.design_selection_binding, binding)
        challenge = host.request_design_selection(
            flow.workflow_id,
            flow.revision,
            FrontendKind.JLCEDA,
            timedelta(minutes=1),
        )
        connection = host.connect_frontend(FrontendKind.JLCEDA, "production-jlceda")
        selected_token = candidate_choice_tokens(binding)[0][0]
        original = design_selection_disambiguation.issue_trusted_design_selection_decision
        with patch.object(
            design_selection_disambiguation,
            "issue_trusted_design_selection_decision",
            wraps=original,
        ) as delegated:
            resolved = host.answer_design_selection(
                connection.connection_id,
                challenge.workflow_id,
                challenge.workflow_revision,
                challenge.challenge_id,
                challenge.nonce,
                challenge.binding.candidate_set_identity,
                selected_token,
            )

            self.assertEqual(resolved.state, WorkflowState.TARGET_RESOLVED)
            self.assertIsNotNone(resolved.trusted_design_selection)
            self.assertEqual(resolved.probe_target.design_object, context.nets[0].ref)
            with self.assertRaises(Exception):
                host.answer_design_selection(
                    connection.connection_id,
                    challenge.workflow_id,
                    challenge.workflow_revision,
                    challenge.challenge_id,
                    challenge.nonce,
                    challenge.binding.candidate_set_identity,
                    selected_token,
                )
            self.assertEqual(delegated.call_count, 1)

    def test_changed_observation_rejects_old_answer_without_invoking_factory(self) -> None:
        host = ApplicationHost(
            design_selection_issuer=ProductionDesignSelectionDecisionIssuer(),
            clock=lambda: NOW,
        )
        context = ambiguous_context()
        binding = build_candidate_set_binding(
            selection_context=context,
            selection_observed_at=NOW,
        )
        flow = host.start_workflow("resolve PWM_OUT", "request-stale-selection")
        flow = host.transition(flow.workflow_id, flow.revision, WorkflowState.OBSERVING_DESIGN)
        flow = host.record_design_observation(
            flow.workflow_id,
            flow.revision,
            "sha256:" + "a" * 64,
            selection_context=context,
            candidate_binding=binding,
            probe_target=None,
        )
        challenge = host.request_design_selection(
            flow.workflow_id,
            flow.revision,
            FrontendKind.JLCEDA,
            timedelta(minutes=1),
        )
        host.record_design_observation(
            flow.workflow_id,
            challenge.workflow_revision,
            "sha256:" + "b" * 64,
            selection_context=context,
            candidate_binding=binding,
            probe_target=None,
        )
        connection = host.connect_frontend(FrontendKind.JLCEDA, "stale-jlceda")
        selected_token = candidate_choice_tokens(binding)[0][0]
        with patch.object(
            design_selection_disambiguation,
            "issue_trusted_design_selection_decision",
        ) as delegated:
            with self.assertRaises(Exception):
                host.answer_design_selection(
                    connection.connection_id,
                    challenge.workflow_id,
                    challenge.workflow_revision,
                    challenge.challenge_id,
                    challenge.nonce,
                    challenge.binding.candidate_set_identity,
                    selected_token,
                )
        delegated.assert_not_called()

    def test_changed_candidate_set_rejects_old_answer_without_label_reconstruction(self) -> None:
        host = ApplicationHost(
            design_selection_issuer=ProductionDesignSelectionDecisionIssuer(),
            clock=lambda: NOW,
        )
        old_context = ambiguous_context()
        old_binding = build_candidate_set_binding(
            selection_context=old_context,
            selection_observed_at=NOW,
        )
        flow = host.start_workflow("resolve PWM_OUT", "request-changed-candidates")
        flow = host.transition(flow.workflow_id, flow.revision, WorkflowState.OBSERVING_DESIGN)
        flow = host.record_design_observation(
            flow.workflow_id,
            flow.revision,
            "sha256:" + "a" * 64,
            selection_context=old_context,
            candidate_binding=old_binding,
            probe_target=None,
        )
        challenge = host.request_design_selection(
            flow.workflow_id,
            flow.revision,
            FrontendKind.JLCEDA,
            timedelta(minutes=1),
        )
        new_context = changed_ambiguous_context(old_context)
        new_binding = build_candidate_set_binding(
            selection_context=new_context,
            selection_observed_at=NOW + timedelta(seconds=1),
        )
        host.record_design_observation(
            flow.workflow_id,
            challenge.workflow_revision,
            "sha256:" + "b" * 64,
            selection_context=new_context,
            candidate_binding=new_binding,
            probe_target=None,
        )
        connection = host.connect_frontend(FrontendKind.JLCEDA, "changed-jlceda")
        old_token = candidate_choice_tokens(old_binding)[0][0]
        with patch.object(
            design_selection_disambiguation,
            "issue_trusted_design_selection_decision",
        ) as delegated:
            with self.assertRaises(Exception):
                host.answer_design_selection(
                    connection.connection_id,
                    challenge.workflow_id,
                    challenge.workflow_revision,
                    challenge.challenge_id,
                    challenge.nonce,
                    challenge.binding.candidate_set_identity,
                    old_token,
                )
        delegated.assert_not_called()


if __name__ == "__main__":
    unittest.main()
