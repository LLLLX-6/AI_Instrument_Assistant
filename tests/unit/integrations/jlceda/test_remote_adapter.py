from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from ai_instrument_assistant.application.ports.eda_interface import (
    CapabilityUnsupportedError,
    EDAConnectionLostError,
    EDACapability,
    EDANotConnectedError,
    EDARequestTimeoutError,
    InconsistentDesignObservationError,
    NoActiveDocumentError,
)
from ai_instrument_assistant.domain.eda.models import DesignObjectKind
from ai_instrument_assistant.integrations.jlceda.errors import (
    JLCEDAConnectionLostError,
    JLCEDARequestTimeoutError,
    JLCEDATransportUnavailableError,
)
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.remote_adapter import (
    JLCEDARemoteAdapter,
)
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


ROOT = Path(__file__).resolve().parents[4]
PROTOCOL_ROOT = ROOT / "protocols" / "jlceda" / "v1"


class StubRequestClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, object, float]] = []

    async def request(
        self, operation: str, payload: object, *, timeout: float
    ) -> object:
        self.calls.append((operation, payload, timeout))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class JLCEDARemoteAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.validator = SchemaValidator(SchemaRegistry.from_directory(PROTOCOL_ROOT))

    async def test_maps_valid_response_to_provider_neutral_document(self) -> None:
        client = StubRequestClient(_success_response())
        adapter = JLCEDARemoteAdapter(
            request_client=client,
            validator=self.validator,
            mapper=JLCEDADomainMapper(),
            request_timeout=1.25,
        )

        document = await adapter.get_active_document()

        self.assertEqual("jlceda-pro", document.document_ref.provider)
        self.assertEqual("official-document-uuid", document.document_ref.native_id)
        self.assertIsNone(document.document_name)
        self.assertIsNone(document.fingerprint)
        self.assertIsNone(document.is_dirty)
        self.assertEqual(
            [("eda.document.get_active", {}, 1.25)], client.calls
        )
        self.assertTrue(adapter.capabilities.supports(EDACapability.DOCUMENT_READ))
        self.assertTrue(adapter.capabilities.supports(EDACapability.SELECTION_READ))

    async def test_maps_valid_wire_selection_to_provider_neutral_context(self) -> None:
        response = _selection_response("wire-net-response.case.json")
        client = StubRequestClient(response)
        adapter = JLCEDARemoteAdapter(
            request_client=client,
            validator=self.validator,
            mapper=JLCEDADomainMapper(),
            request_timeout=1.25,
        )

        context = await adapter.get_selection()

        selected = context.selection.selected_objects[0]
        self.assertIs(selected.object_type, DesignObjectKind.WIRE)
        self.assertEqual("Wire", selected.provider_kind)
        self.assertEqual("wire-1", selected.native_id)
        self.assertEqual("PWM_OUT", selected.display_name)
        self.assertIsNone(context.selection.primary_object)
        self.assertEqual(1, len(context.nets))
        self.assertEqual("PWM_OUT", context.nets[0].ref.display_name)
        self.assertIsNone(context.nets[0].ref.native_id)
        self.assertTrue(context.nets[0].connectivity_unresolved)
        self.assertIsNone(context.nets[0].signal_expectation)
        self.assertEqual([("eda.selection.get", {}, 1.25)], client.calls)

    async def test_empty_remote_selection_is_valid(self) -> None:
        context = await self._adapter(
            _selection_response("empty-selection-response.case.json")
        ).get_selection()

        self.assertEqual((), context.selection.selected_objects)
        self.assertEqual((), context.nets)

    async def test_full_design_operation_maps_provider_neutral_observation(self) -> None:
        fixture = PROTOCOL_ROOT / "fixtures" / "valid" / "design-observation" / "rc-low-pass.case.json"
        observation = json.loads(fixture.read_text(encoding="utf-8"))["instance"]
        response = _base() | {
            "operation": "eda.design.get",
            "status": "success",
            "payload": {"observation": observation},
        }
        client = StubRequestClient(response)
        adapter = JLCEDARemoteAdapter(
            request_client=client, validator=self.validator, mapper=JLCEDADomainMapper()
        )

        result = await adapter.observe_design()

        self.assertEqual(2, len(result.components))
        self.assertEqual([("eda.design.get", {}, 5.0)], client.calls)
        self.assertTrue(adapter.capabilities.supports(EDACapability.DESIGN_READ))

    async def test_selection_maps_inconsistent_observation_error(self) -> None:
        adapter = self._adapter(
            _selection_error_response("inconsistent_observation")
        )
        with self.assertRaises(InconsistentDesignObservationError):
            await adapter.get_selection()

    async def test_selection_rejects_raw_transport_dto_leak(self) -> None:
        response = _selection_response("wire-net-response.case.json")
        response["payload"]["totalSelected"] = 1
        adapter = self._adapter(response)
        with self.assertRaisesRegex(RuntimeError, "protocol"):
            await adapter.get_selection()

    async def test_selection_maps_transport_timeout(self) -> None:
        adapter = self._adapter(JLCEDARequestTimeoutError("late"))
        with self.assertRaises(EDARequestTimeoutError):
            await adapter.get_selection()

    async def test_maps_structured_no_document_error(self) -> None:
        adapter = self._adapter(_error_response("no_active_document"))
        with self.assertRaises(NoActiveDocumentError):
            await adapter.get_active_document()

    async def test_maps_structured_unsupported_error(self) -> None:
        adapter = self._adapter(_error_response("capability_unsupported"))
        with self.assertRaises(CapabilityUnsupportedError):
            await adapter.get_active_document()

    async def test_rejects_malformed_remote_response_before_mapping(self) -> None:
        response = _success_response()
        response["payload"]["document"]["tabId"] = "must-not-cross-boundary"
        adapter = self._adapter(response)
        with self.assertRaisesRegex(RuntimeError, "protocol"):
            await adapter.get_active_document()

    async def test_maps_transport_failures_to_provider_neutral_port_errors(self) -> None:
        cases = (
            (JLCEDATransportUnavailableError("offline"), EDANotConnectedError),
            (JLCEDARequestTimeoutError("late"), EDARequestTimeoutError),
            (JLCEDAConnectionLostError("gone"), EDAConnectionLostError),
        )
        for transport_error, port_error in cases:
            with self.subTest(error=type(transport_error).__name__):
                with self.assertRaises(port_error):
                    await self._adapter(transport_error).get_active_document()

    def _adapter(self, response: object) -> JLCEDARemoteAdapter:
        return JLCEDARemoteAdapter(
            request_client=StubRequestClient(response),
            validator=self.validator,
            mapper=JLCEDADomainMapper(),
        )


def _base() -> dict[str, Any]:
    return {
        "protocol": "aia-jlceda",
        "protocol_version": "1.0",
        "message_id": "44444444-4444-4444-8444-444444444444",
        "sent_at": "2026-09-05T08:00:00Z",
        "trace_id": "22222222-2222-4222-8222-222222222222",
        "session_id": "33333333-3333-4333-8333-333333333333",
        "kind": "response",
        "operation": "eda.document.get_active",
        "reply_to_message_id": "11111111-1111-4111-8111-111111111111",
    }


def _success_response() -> dict[str, Any]:
    return _base() | {
        "status": "success",
        "payload": {
            "document": {
                "model_version": "1.0",
                "document_ref": {
                    "model_version": "1.0",
                    "provider": "jlceda-pro",
                    "object_type": "document",
                    "document_id": "official-document-uuid",
                    "snapshot_id": "55555555-5555-4555-8555-555555555555",
                    "native_id": "official-document-uuid",
                    "canonical_id": "jlceda-pro:document:official-document-uuid",
                    "display_name": None,
                },
                "project_id": None,
                "project_name": None,
                "document_name": None,
                "document_type": "schematic",
                "native_revision": None,
                "fingerprint": None,
                "is_dirty": None,
                "captured_at": "2026-09-05T08:00:00Z",
            }
        },
    }


def _error_response(code: str) -> dict[str, Any]:
    return _base() | {
        "status": "error",
        "error": {"code": code, "message": "bounded remote error"},
    }


def _selection_response(name: str) -> dict[str, Any]:
    fixture = PROTOCOL_ROOT / "fixtures" / "valid" / "eda-selection" / name
    return json.loads(fixture.read_text(encoding="utf-8"))["instance"]


def _selection_error_response(code: str) -> dict[str, Any]:
    response = _selection_response("empty-selection-response.case.json")
    response.pop("payload")
    response["status"] = "error"
    response["error"] = {"code": code, "message": "bounded remote error"}
    return response


if __name__ == "__main__":
    unittest.main()
