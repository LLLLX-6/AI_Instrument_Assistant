from __future__ import annotations

import unittest
from dataclasses import fields
from datetime import datetime, timezone
from uuid import uuid4

from ai_instrument_assistant.application.interactive import (
    ConnectionState,
    HardwareState,
    HostState,
    ProductStatus,
    ProductErrorCode,
    PRODUCT_ERROR_MESSAGES,
    WorkflowSession,
    WorkflowState,
    project_product_status,
    safe_message_for,
    ApplicationHost,
    FrontendKind,
)
from tests.support.interactive_fakes import FakeTrustedDecisionIssuer


class ProductStatusTests(unittest.TestCase):
    def test_every_stable_error_code_maps_to_bounded_safe_text(self) -> None:
        self.assertEqual(set(PRODUCT_ERROR_MESSAGES), set(ProductErrorCode))
        for code in ProductErrorCode:
            with self.subTest(code=code):
                message = safe_message_for(code)
                self.assertTrue(message)
                self.assertLessEqual(len(message), 256)

    def test_projection_is_whitelisted_and_sanitized(self) -> None:
        workflow = WorkflowSession(
            uuid4(), 2, "request-1", "  inspect\nPWM_OUT  ", WorkflowState.TARGET_RESOLVED
        )
        status = project_product_status(
            host_state=HostState.READY,
            protocol_compatible=True,
            harness_connected=True,
            jlceda_connected=False,
            hardware_state=HardwareState.AVAILABLE,
            workflow=workflow,
            message="  Ready\nfor bounded interaction.  ",
        )
        self.assertEqual(status.harness_state, ConnectionState.CONNECTED)
        self.assertEqual(status.jlceda_state, ConnectionState.DISCONNECTED)
        self.assertEqual(status.safe_workflow_label, "inspect PWM_OUT")
        self.assertEqual(status.message, "Ready for bounded interaction.")
        forbidden = {
            "port", "pid", "path", "visa_resource", "scpi", "serial",
            "api_key", "provider_payload", "raw_model_candidate", "waveform",
        }
        self.assertTrue(forbidden.isdisjoint({item.name for item in fields(ProductStatus)}))

    def test_host_status_reflects_connections_without_exposing_authentication(self) -> None:
        host = ApplicationHost(
            trusted_issuer=FakeTrustedDecisionIssuer(),
            clock=lambda: datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        host.connect_frontend(FrontendKind.HARNESS, "opaque-authenticated-principal")
        status = host.record_hardware_status(HardwareState.AVAILABLE)
        self.assertEqual(status.harness_state, ConnectionState.CONNECTED)
        self.assertEqual(status.hardware_state, HardwareState.AVAILABLE)
        self.assertNotIn("opaque-authenticated-principal", repr(status))

        status = host.record_hardware_status(
            HardwareState.UNAVAILABLE, ProductErrorCode.INSTRUMENT_DISCONNECTED
        )
        self.assertEqual(
            status.message,
            "The instrument connection was lost.",
        )


if __name__ == "__main__":
    unittest.main()
