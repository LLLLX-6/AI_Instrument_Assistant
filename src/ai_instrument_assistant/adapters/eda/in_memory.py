from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from ai_instrument_assistant.application.ports.eda_interface import (
    DesignObjectNotFoundError,
    EDACapability,
    EDACapabilitySet,
    EDAInterface,
    HighlightCommand,
    HighlightResult,
    HighlightStatus,
    NoActiveDocumentError,
    StaleDesignSnapshotError,
)
from ai_instrument_assistant.domain.eda.models import (
    CircuitEndpoint,
    CircuitNet,
    DesignDocument,
    DesignObjectKind,
    DesignObjectRef,
    DesignSelection,
    DutyCycle,
    SelectionContext,
    SignalExpectation,
)


_ALL_CAPABILITIES = EDACapabilitySet(frozenset(EDACapability))
_PWM_SNAPSHOT_ID = UUID("11111111-1111-4111-8111-111111111111")


class InMemoryEDAAdapter(EDAInterface):
    """Deterministic async EDA adapter backed only by Domain objects."""

    def __init__(
        self,
        active_document: DesignDocument | None,
        selection_context: SelectionContext,
        *,
        capabilities: EDACapabilitySet = _ALL_CAPABILITIES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if active_document is not None and (
            selection_context.snapshot_id != active_document.snapshot_id
            or selection_context.selection.document_ref.provider
            != active_document.document_ref.provider
            or selection_context.selection.document_ref.document_id
            != active_document.document_ref.document_id
        ):
            raise ValueError(
                "selection context must belong to the active document snapshot"
            )
        self._active_document = active_document
        self._selection_context = selection_context
        self._capabilities = capabilities
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._highlight_history: list[HighlightCommand] = []
        self._idempotency_keys: set[str] = set()

    @classmethod
    def for_pwm_out_scenario(
        cls,
        *,
        capabilities: EDACapabilitySet = _ALL_CAPABILITIES,
        clock: Callable[[], datetime] | None = None,
    ) -> InMemoryEDAAdapter:
        document_ref = DesignObjectRef(
            provider="jlceda-pro",
            object_type=DesignObjectKind.DOCUMENT,
            document_id="doc-main-schematic",
            snapshot_id=_PWM_SNAPSHOT_ID,
            native_id="doc-main-schematic",
            canonical_id="jlceda-pro:project-stm32-test:doc-main-schematic:document",
            display_name="main_schematic",
        )
        net_ref = DesignObjectRef(
            provider="jlceda-pro",
            object_type=DesignObjectKind.NET,
            document_id="doc-main-schematic",
            snapshot_id=_PWM_SNAPSHOT_ID,
            native_id="net-pwm-out",
            canonical_id=(
                "jlceda-pro:project-stm32-test:doc-main-schematic:net:pwm-out"
            ),
            display_name="PWM_OUT",
        )
        document = DesignDocument(
            document_ref=document_ref,
            project_id="project-stm32-test",
            project_name="STM32_Test",
            document_name="main_schematic",
            document_type="schematic",
            native_revision=None,
            content_fingerprint="sha256:pwm-out-slice-v1",
            fingerprint_scope_kind="selected_context",
            fingerprint_scope_version="1.0",
            fingerprint_scope=("document", "selection", "selected_nets"),
            is_dirty=False,
            captured_at=datetime(2026, 8, 22, 0, 0, tzinfo=timezone.utc),
        )
        source = CircuitEndpoint(component_reference="U1", pin_name="PA0")
        net = CircuitNet(
            ref=net_ref,
            endpoints=(source,),
            source=source,
            signal_expectation=SignalExpectation(
                frequency_hz=10_000.0,
                duty_cycle=DutyCycle.from_ratio(0.30),
            ),
        )
        selection = DesignSelection(
            document_ref=document_ref,
            selected_objects=(net_ref,),
            primary_object=net_ref,
        )
        return cls(
            document,
            SelectionContext(selection=selection, nets=(net,)),
            capabilities=capabilities,
            clock=clock,
        )

    @property
    def capabilities(self) -> EDACapabilitySet:
        return self._capabilities

    @property
    def active_document(self) -> DesignDocument | None:
        return self._active_document

    @property
    def selection_context(self) -> SelectionContext:
        return self._selection_context

    @property
    def highlight_history(self) -> tuple[HighlightCommand, ...]:
        return tuple(self._highlight_history)

    async def get_active_document(self) -> DesignDocument:
        self.capabilities.require(EDACapability.DOCUMENT_READ)
        if self._active_document is None:
            raise NoActiveDocumentError("the in-memory EDA has no active document")
        return self._active_document

    async def get_selection(self) -> SelectionContext:
        self.capabilities.require(EDACapability.SELECTION_READ)
        if self._active_document is None:
            raise NoActiveDocumentError("the in-memory EDA has no active document")
        return self._selection_context

    async def highlight(self, command: HighlightCommand) -> HighlightResult:
        self.capabilities.require(EDACapability.VIEW_HIGHLIGHT)
        document = self._active_document
        if document is None:
            raise NoActiveDocumentError("the in-memory EDA has no active document")
        self._require_current_guard(command, document)
        self._require_known_targets(command)

        if command.idempotency_key in self._idempotency_keys:
            return HighlightResult(
                status=HighlightStatus.NOOP,
                warnings=("idempotency key was already applied",),
            )

        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        expires_at = now + command.ttl if command.ttl is not None else None
        self._idempotency_keys.add(command.idempotency_key)
        self._highlight_history.append(command)
        return HighlightResult(
            status=HighlightStatus.APPLIED,
            applied_targets=command.targets,
            expires_at=expires_at,
        )

    def set_empty_selection(self) -> None:
        document = self._active_document
        if document is None:
            raise NoActiveDocumentError("the in-memory EDA has no active document")
        self._selection_context = SelectionContext(
            selection=DesignSelection(document_ref=document.document_ref),
        )

    def advance_snapshot(
        self,
        snapshot_id: UUID,
        *,
        content_fingerprint: str,
    ) -> None:
        document = self._active_document
        if document is None:
            raise NoActiveDocumentError("the in-memory EDA has no active document")

        old_context = self._selection_context
        new_document_ref = replace(document.document_ref, snapshot_id=snapshot_id)
        new_refs = {
            ref.canonical_id: replace(ref, snapshot_id=snapshot_id)
            for ref in old_context.selection.selected_objects
        }
        selected_objects = tuple(
            new_refs[ref.canonical_id]
            for ref in old_context.selection.selected_objects
        )
        primary = old_context.selection.primary_object
        new_primary = None if primary is None else new_refs[primary.canonical_id]
        new_selection = DesignSelection(
            document_ref=new_document_ref,
            selected_objects=selected_objects,
            primary_object=new_primary,
        )
        new_nets = tuple(
            replace(net, ref=new_refs[net.ref.canonical_id])
            for net in old_context.nets
        )
        self._active_document = replace(
            document,
            document_ref=new_document_ref,
            content_fingerprint=content_fingerprint,
            captured_at=self._clock(),
        )
        self._selection_context = SelectionContext(
            selection=new_selection,
            nets=new_nets,
        )

    @staticmethod
    def _require_current_guard(
        command: HighlightCommand,
        document: DesignDocument,
    ) -> None:
        ref = document.document_ref
        guarded_ref = command.document_ref
        if (
            guarded_ref.provider != ref.provider
            or guarded_ref.document_id != ref.document_id
            or guarded_ref.canonical_id != ref.canonical_id
            or command.expected_snapshot_id != document.snapshot_id
            or command.expected_content_fingerprint != document.content_fingerprint
            or command.expected_fingerprint_scope_kind
            != document.fingerprint_scope_kind
            or command.expected_fingerprint_scope_version
            != document.fingerprint_scope_version
            or command.expected_fingerprint_scope != document.fingerprint_scope
        ):
            raise StaleDesignSnapshotError(
                "highlight guard does not match the active design snapshot"
            )

    def _require_known_targets(self, command: HighlightCommand) -> None:
        known_refs = set(self._selection_context.selection.selected_objects)
        unknown = tuple(target for target in command.targets if target not in known_refs)
        if unknown:
            raise DesignObjectNotFoundError(
                "highlight target is not present in the in-memory design context"
            )
