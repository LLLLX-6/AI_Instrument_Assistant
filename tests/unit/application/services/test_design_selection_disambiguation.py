from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

from ai_instrument_assistant.application.services.design_selection_disambiguation import (
    CANDIDATE_FINGERPRINT_SCOPE,
    DesignSelectionCandidateIdentity,
    DesignSelectionCandidateSetBinding,
    TrustedDesignSelectionDecision,
    TrustedDesignSelectionOrigin,
    TrustedDesignSelectionReason,
    TrustedDesignSelectionResolutionStatus,
    build_candidate_set_binding,
    candidate_choice_tokens,
    issue_trusted_design_selection_decision,
    resolve_trusted_design_selection,
)
from ai_instrument_assistant.domain.eda.models import (
    CircuitNet,
    DesignObjectKind,
    DesignObjectRef,
    DesignSelection,
    ProbeTargetKind,
    SelectionContext,
)
from ai_instrument_assistant.domain.errors import DomainInvariantError


SNAPSHOT = UUID("11111111-1111-4111-8111-111111111111")
OTHER_SNAPSHOT = UUID("22222222-2222-4222-8222-222222222222")
DECISION_ID = UUID("33333333-3333-4333-8333-333333333333")
OBSERVED_AT = datetime(2026, 9, 11, 1, 0, tzinfo=timezone.utc)
DECIDED_AT = OBSERVED_AT + timedelta(seconds=1)
WORKFLOW = "phase8b2-real-jlceda-recorded"
REQUEST = "phase8b2-request-1"


def ref(
    kind: DesignObjectKind,
    canonical_id: str,
    *,
    snapshot_id: UUID = SNAPSHOT,
    document_id: str = "main-schematic",
    display_name: str | None = None,
    provider: str = "jlceda-pro",
) -> DesignObjectRef:
    return DesignObjectRef(
        provider=provider,
        object_type=kind,
        document_id=document_id,
        snapshot_id=snapshot_id,
        native_id=f"native-{canonical_id}",
        canonical_id=canonical_id,
        display_name=display_name,
        provider_kind=kind.value.title(),
    )


def context(
    *,
    selected: tuple[DesignObjectRef, ...] | None = None,
    nets: tuple[CircuitNet, ...] | None = None,
    snapshot_id: UUID = SNAPSHOT,
    document_id: str = "main-schematic",
) -> SelectionContext:
    document = ref(
        DesignObjectKind.DOCUMENT,
        f"jlceda-pro:document:{document_id}",
        snapshot_id=snapshot_id,
        document_id=document_id,
    )
    wire = ref(
        DesignObjectKind.WIRE,
        "jlceda-pro:wire:wire-a",
        snapshot_id=snapshot_id,
        document_id=document_id,
        display_name="PWM_OUT",
    )
    component = ref(
        DesignObjectKind.COMPONENT,
        "jlceda-pro:component:u1",
        snapshot_id=snapshot_id,
        document_id=document_id,
    )
    net = CircuitNet(
        ref=ref(
            DesignObjectKind.NET,
            "jlceda-pro:net:PWM_OUT",
            snapshot_id=snapshot_id,
            document_id=document_id,
            display_name="PWM_OUT",
        ),
        endpoints=(),
    )
    return SelectionContext(
        selection=DesignSelection(
            document_ref=document,
            selected_objects=(wire, component) if selected is None else selected,
            primary_object=None,
        ),
        nets=(net,) if nets is None else nets,
    )


def binding(value: SelectionContext | None = None, *, observed_at=OBSERVED_AT):
    return build_candidate_set_binding(
        selection_context=context() if value is None else value,
        selection_observed_at=observed_at,
    )


def decision(
    value: DesignSelectionCandidateSetBinding | None = None,
    *,
    chosen: DesignObjectRef | None = None,
    workflow_id: str = WORKFLOW,
    request_id: str = REQUEST,
    decided_at=DECIDED_AT,
) -> TrustedDesignSelectionDecision:
    current = binding() if value is None else value
    selected = current.presented_candidates[0] if chosen is None else chosen
    return issue_trusted_design_selection_decision(
        decision_id=DECISION_ID,
        candidate_binding=current,
        selected_candidate=DesignSelectionCandidateIdentity.from_ref(selected),
        workflow_id=workflow_id,
        request_correlation_id=request_id,
        decided_at=decided_at,
    )


def resolve(
    current: SelectionContext | None = None,
    *,
    current_binding: DesignSelectionCandidateSetBinding | None = None,
    trusted_decision: TrustedDesignSelectionDecision | None = None,
    workflow_id: str = WORKFLOW,
    request_id: str = REQUEST,
):
    current_context = context() if current is None else current
    current_bound = binding(current_context) if current_binding is None else current_binding
    return resolve_trusted_design_selection(
        current_selection=current_context,
        current_binding=current_bound,
        decision=trusted_decision,
        trusted_workflow_id=workflow_id,
        trusted_request_correlation_id=request_id,
    )


class CandidateIdentityAndBindingTests(unittest.TestCase):
    def test_identity_uses_only_bounded_stable_fields(self) -> None:
        wire = context().selection.selected_objects[0]
        identity = DesignSelectionCandidateIdentity.from_ref(wire)
        renamed = replace(wire, display_name="RENAMED", provider_kind="ProviderWireV2")
        self.assertEqual(identity, DesignSelectionCandidateIdentity.from_ref(renamed))
        self.assertFalse(hasattr(identity, "display_name"))
        self.assertFalse(hasattr(identity, "provider_kind"))
        self.assertFalse(hasattr(identity, "native_id"))

    def test_same_display_name_with_different_canonical_id_is_different(self) -> None:
        wire = context().selection.selected_objects[0]
        other = replace(wire, canonical_id="jlceda-pro:wire:wire-b")
        self.assertNotEqual(
            DesignSelectionCandidateIdentity.from_ref(wire),
            DesignSelectionCandidateIdentity.from_ref(other),
        )

    def test_reversed_provider_order_has_same_fingerprint(self) -> None:
        original = context()
        reversed_context = replace(
            original,
            selection=replace(
                original.selection,
                selected_objects=tuple(reversed(original.selection.selected_objects)),
            ),
        )
        first = binding(original)
        second = binding(reversed_context)
        self.assertEqual(first.candidate_set_fingerprint, second.candidate_set_fingerprint)
        self.assertEqual(first.fingerprint_scope, CANDIDATE_FINGERPRINT_SCOPE)
        self.assertNotEqual(first.presented_candidates, second.presented_candidates)

    def test_changed_identity_changes_fingerprint(self) -> None:
        original = context()
        changed_wire = replace(
            original.selection.selected_objects[0],
            canonical_id="jlceda-pro:wire:wire-c",
        )
        changed = replace(
            original,
            selection=replace(
                original.selection,
                selected_objects=(changed_wire, original.selection.selected_objects[1]),
            ),
        )
        self.assertNotEqual(
            binding(original).candidate_set_fingerprint,
            binding(changed).candidate_set_fingerprint,
        )

    def test_choice_tokens_are_opaque_and_do_not_contain_labels(self) -> None:
        current = binding()
        tokens = candidate_choice_tokens(current)
        self.assertEqual(len(tokens), 2)
        self.assertEqual({identity for _, identity in tokens}, set(current.candidate_identities))
        self.assertTrue(all("PWM_OUT" not in token for token, _ in tokens))


class TrustedDecisionIssuanceTests(unittest.TestCase):
    def test_valid_exact_candidate_is_issued_from_closed_trusted_origin(self) -> None:
        issued = decision()
        self.assertEqual(issued.trusted_origin, TrustedDesignSelectionOrigin.TRUSTED_HOST_USER_EVENT)
        self.assertEqual(issued.selected_object, binding().presented_candidates[0])

    def test_free_text_or_display_name_cannot_create_decision(self) -> None:
        with self.assertRaises(DomainInvariantError):
            issue_trusted_design_selection_decision(
                decision_id=DECISION_ID,
                candidate_binding=binding(),
                selected_candidate="PWM_OUT",
                workflow_id=WORKFLOW,
                request_correlation_id=REQUEST,
                decided_at=DECIDED_AT,
            )

    def test_arbitrary_design_object_ref_injection_is_rejected(self) -> None:
        unrelated = ref(
            DesignObjectKind.WIRE,
            "jlceda-pro:wire:unrelated",
            display_name="PWM_OUT",
        )
        with self.assertRaises(DomainInvariantError):
            issue_trusted_design_selection_decision(
                decision_id=DECISION_ID,
                candidate_binding=binding(),
                selected_candidate=DesignSelectionCandidateIdentity.from_ref(unrelated),
                workflow_id=WORKFLOW,
                request_correlation_id=REQUEST,
                decided_at=DECIDED_AT,
            )

    def test_decision_cannot_be_directly_instantiated_from_external_json(self) -> None:
        with self.assertRaises(TypeError):
            TrustedDesignSelectionDecision(
                decision_id=str(DECISION_ID),
                workflow_id=WORKFLOW,
                request_correlation_id=REQUEST,
            )


class TrustedResolutionTests(unittest.TestCase):
    def test_wire_component_without_decision_remains_ambiguous(self) -> None:
        result = resolve()
        self.assertEqual(result.status, TrustedDesignSelectionResolutionStatus.DECISION_REQUIRED)
        self.assertEqual(result.reason, TrustedDesignSelectionReason.TRUSTED_DECISION_REQUIRED)
        self.assertIsNone(result.probe_target)

    def test_exact_wire_choice_resolves_and_creates_design_only_net_probe(self) -> None:
        current = context()
        current_binding = binding(current)
        result = resolve(
            current,
            current_binding=current_binding,
            trusted_decision=decision(current_binding),
        )
        self.assertEqual(result.status, TrustedDesignSelectionResolutionStatus.RESOLVED)
        self.assertEqual(result.chosen_candidate.object_type, DesignObjectKind.WIRE)
        self.assertEqual(result.derived_target.object_type, DesignObjectKind.NET)
        self.assertEqual(result.probe_target.kind, ProbeTargetKind.DESIGN_ONLY)
        self.assertIsNone(result.probe_target.physical_location)

    def test_component_and_null_provider_primary_are_preserved(self) -> None:
        current = context()
        current_binding = binding(current)
        result = resolve(
            current,
            current_binding=current_binding,
            trusted_decision=decision(current_binding),
        )
        self.assertEqual(result.provider_selection, current)
        self.assertEqual(len(result.provider_selection.selection.selected_objects), 2)
        self.assertTrue(
            any(
                item.object_type is DesignObjectKind.COMPONENT
                for item in result.provider_selection.selection.selected_objects
            )
        )
        self.assertIsNone(result.provider_selection.selection.primary_object)

    def test_component_choice_is_unsupported_and_never_uses_wire_net(self) -> None:
        current = context()
        current_binding = binding(current)
        component = current.selection.selected_objects[1]
        result = resolve(
            current,
            current_binding=current_binding,
            trusted_decision=decision(current_binding, chosen=component),
        )
        self.assertEqual(result.status, TrustedDesignSelectionResolutionStatus.UNSUPPORTED_CHOICE)
        self.assertEqual(result.reason, TrustedDesignSelectionReason.CHOSEN_OBJECT_UNSUPPORTED)
        self.assertIsNone(result.derived_target)
        self.assertIsNone(result.probe_target)

    def test_workflow_mismatch_fails_closed(self) -> None:
        current_binding = binding()
        result = resolve(
            current_binding=current_binding,
            trusted_decision=decision(current_binding),
            workflow_id="other-workflow",
        )
        self.assertEqual(result.reason, TrustedDesignSelectionReason.WORKFLOW_MISMATCH)
        self.assertIsNone(result.probe_target)

    def test_request_mismatch_fails_closed(self) -> None:
        current_binding = binding()
        result = resolve(
            current_binding=current_binding,
            trusted_decision=decision(current_binding),
            request_id="other-request",
        )
        self.assertEqual(result.reason, TrustedDesignSelectionReason.REQUEST_MISMATCH)

    def test_document_mismatch_fails_closed(self) -> None:
        old = context(document_id="old-document")
        old_binding = binding(old)
        result = resolve(trusted_decision=decision(old_binding))
        self.assertEqual(result.reason, TrustedDesignSelectionReason.DOCUMENT_MISMATCH)

    def test_snapshot_mismatch_fails_closed(self) -> None:
        old = context(snapshot_id=OTHER_SNAPSHOT)
        old_binding = binding(old)
        result = resolve(trusted_decision=decision(old_binding))
        self.assertEqual(result.reason, TrustedDesignSelectionReason.SNAPSHOT_MISMATCH)

    def test_same_canonical_id_under_new_snapshot_cannot_reuse_decision(self) -> None:
        old = context(snapshot_id=OTHER_SNAPSHOT)
        old_binding = binding(old)
        result = resolve(trusted_decision=decision(old_binding))
        self.assertNotEqual(result.status, TrustedDesignSelectionResolutionStatus.RESOLVED)
        self.assertIsNone(result.probe_target)

    def test_changed_candidate_set_invalidates_decision(self) -> None:
        old_binding = binding()
        current = context()
        changed_component = replace(
            current.selection.selected_objects[1],
            canonical_id="jlceda-pro:component:u2",
        )
        changed = replace(
            current,
            selection=replace(
                current.selection,
                selected_objects=(current.selection.selected_objects[0], changed_component),
            ),
        )
        result = resolve(changed, trusted_decision=decision(old_binding))
        self.assertEqual(result.reason, TrustedDesignSelectionReason.CANDIDATE_SET_MISMATCH)

    def test_stale_decision_predating_current_observation_is_rejected(self) -> None:
        old_binding = binding(observed_at=OBSERVED_AT)
        issued = decision(old_binding, decided_at=DECIDED_AT)
        current_binding = binding(observed_at=DECIDED_AT + timedelta(seconds=1))
        result = resolve(current_binding=current_binding, trusted_decision=issued)
        self.assertEqual(result.reason, TrustedDesignSelectionReason.STALE_DECISION)

    def test_changed_observation_time_cannot_reuse_decision(self) -> None:
        old_binding = binding(observed_at=OBSERVED_AT)
        issued = decision(old_binding, decided_at=DECIDED_AT + timedelta(seconds=2))
        current_binding = binding(observed_at=OBSERVED_AT + timedelta(seconds=1))
        result = resolve(current_binding=current_binding, trusted_decision=issued)
        self.assertEqual(
            result.reason,
            TrustedDesignSelectionReason.OBSERVATION_TIME_MISMATCH,
        )
        self.assertIsNone(result.probe_target)

    def test_chosen_candidate_disappearing_is_rejected(self) -> None:
        old_binding = binding()
        current = context()
        only_component = current.selection.selected_objects[1]
        replacement = ref(
            DesignObjectKind.WIRE,
            "jlceda-pro:wire:replacement",
            display_name="PWM_OUT",
        )
        changed = replace(
            current,
            selection=replace(
                current.selection,
                selected_objects=(replacement, only_component),
            ),
        )
        result = resolve(changed, trusted_decision=decision(old_binding))
        self.assertIn(
            result.reason,
            {
                TrustedDesignSelectionReason.CHOSEN_CANDIDATE_ABSENT,
                TrustedDesignSelectionReason.CANDIDATE_SET_MISMATCH,
            },
        )

    def test_fingerprint_mismatch_fails_closed(self) -> None:
        current = binding()
        tampered = DesignSelectionCandidateSetBinding(
            document_ref=current.document_ref,
            selection_observed_at=current.selection_observed_at,
            presented_candidates=current.presented_candidates,
            candidate_identities=current.candidate_identities,
            fingerprint_scope=current.fingerprint_scope,
            candidate_set_fingerprint="sha256:" + "0" * 64,
        )
        result = resolve(current_binding=tampered, trusted_decision=decision(current))
        self.assertEqual(result.reason, TrustedDesignSelectionReason.FINGERPRINT_MISMATCH)

    def test_multiple_derived_nets_remain_ambiguous(self) -> None:
        current = context()
        second_net = CircuitNet(
            ref=replace(
                current.nets[0].ref,
                canonical_id="jlceda-pro:net:SECOND",
                display_name="SECOND",
            ),
            endpoints=(),
        )
        current = replace(current, nets=(current.nets[0], second_net))
        current_binding = binding(current)
        result = resolve(
            current,
            current_binding=current_binding,
            trusted_decision=decision(current_binding),
        )
        self.assertEqual(
            result.status,
            TrustedDesignSelectionResolutionStatus.DERIVED_TARGET_AMBIGUOUS,
        )
        self.assertEqual(result.reason, TrustedDesignSelectionReason.MULTIPLE_DERIVED_NETS)
        self.assertIsNone(result.probe_target)

    def test_reordered_current_candidates_preserve_identity_resolution(self) -> None:
        original = context()
        original_binding = binding(original)
        issued = decision(original_binding)
        reordered = replace(
            original,
            selection=replace(
                original.selection,
                selected_objects=tuple(reversed(original.selection.selected_objects)),
            ),
        )
        reordered_binding = binding(reordered)

        result = resolve(
            reordered,
            current_binding=reordered_binding,
            trusted_decision=issued,
        )

        self.assertEqual(result.status, TrustedDesignSelectionResolutionStatus.RESOLVED)
        self.assertEqual(result.chosen_candidate.canonical_id, "jlceda-pro:wire:wire-a")
        self.assertEqual(
            original_binding.candidate_set_fingerprint,
            reordered_binding.candidate_set_fingerprint,
        )

    def test_resolution_creates_no_physical_or_execution_authority(self) -> None:
        current_binding = binding()
        result = resolve(
            current_binding=current_binding,
            trusted_decision=decision(current_binding),
        )
        self.assertFalse(hasattr(result, "probe_setup_confirmation"))
        self.assertFalse(hasattr(result, "trusted_operation_scope"))
        self.assertFalse(hasattr(result, "tool_request"))
        self.assertFalse(hasattr(result, "hardware_result"))


if __name__ == "__main__":
    unittest.main()
