"""Real-HTTP regression tests for the RE-001D private application bridge.

The FAKE E2E mocks ``Re001dApplicationPort``, so the real HTTP transport was
never exercised. These tests must cross the actual boundary:

HTTP server -> response serialization -> actual bytes -> HTTP client -> JSON
decode, because the frozen application structures used to break exactly there.
"""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from types import MappingProxyType

from ai_instrument_assistant.integrations.re001d_application.http_server import (
    _encode_json,
    create_server,
)

try:  # discovery imports this file as a package member
    from .test_service import (
        complete_request,
        prepare_request,
        service,
        simulated_backend_canonical,
    )
except ImportError:  # pragma: no cover - direct-file execution fallback
    from test_service import (
        complete_request,
        prepare_request,
        service,
        simulated_backend_canonical,
    )


class JsonWireEncodingTests(unittest.TestCase):
    """The transport encoder must turn frozen values into plain JSON."""

    def test_frozen_nested_response_becomes_plain_json(self):
        frozen = {
            "outer": MappingProxyType({"plan": MappingProxyType({"channel": 1})}),
            "items": (MappingProxyType({"a": "b"}),),
            "text": "x",
            "count": 3,
            "flag": True,
            "none": None,
        }
        decoded = json.loads(_encode_json(frozen).decode("utf-8"))
        self.assertEqual(
            decoded,
            {
                "outer": {"plan": {"channel": 1}},
                "items": [{"a": "b"}],
                "text": "x",
                "count": 3,
                "flag": True,
                "none": None,
            },
        )

    def test_unknown_object_fails_closed_without_stringification(self):
        class Unknown:
            pass

        with self.assertRaises(TypeError):
            _encode_json({"value": Unknown()})
        with self.assertRaises(TypeError):
            _encode_json([Unknown()])


class RE001DHttpBridgeTests(unittest.TestCase):
    def _serve(self, target):
        server = create_server(target, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        self.addCleanup(server.server_close)
        port = server.server_address[1]
        return f"http://127.0.0.1:{port}/aia-re001d-application/v1/"

    def _post(self, url: str, payload: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_prepare_over_real_http_returns_plain_json(self):
        base = self._serve(service())
        status, payload = self._post(
            base + "prepare",
            prepare_request(workflow="http-prepare-regression", correlation="request-http-1"),
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["protocol"], "aia-re001d-application/v1")
        self.assertEqual(payload["operation"], "prepare")
        self.assertEqual(payload["workflow_id"], "http-prepare-regression")
        self.assertEqual(payload["request_correlation_id"], "request-http-1")
        self.assertEqual(payload["intent"], "RE001D_LITE_SINGLE_POINT")
        self.assertEqual(payload["status"], "CONFIRMATION_REQUIRED")
        plan = payload["plan"]
        self.assertIn("CH1", plan["vin"])
        self.assertIn("CH2", plan["vout"])
        self.assertEqual(plan["reference"], "STM32 GND")
        self.assertEqual(
            plan["operation_sequence"],
            [
                ["hardware.measure_frequency", 1],
                ["hardware.measure_vpp", 1],
                ["hardware.measure_frequency", 2],
                ["hardware.measure_vpp", 2],
            ],
        )
        self.assertIsInstance(payload["wiring_instructions"], str)
        self.assertTrue(payload["wiring_instructions"])

    def test_complete_over_real_http_returns_plain_json(self):
        target = service()
        target.prepare(
            prepare_request(workflow="http-complete-regression", correlation="request-http-2")
        )
        base = self._serve(target)
        status, payload = self._post(
            base + "complete",
            complete_request(workflow="http-complete-regression", correlation="request-http-2"),
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["protocol"], "aia-re001d-application/v1")
        self.assertEqual(payload["operation"], "complete")
        self.assertEqual(payload["status"], "COMPLETED")
        publication = payload["publication"]
        self.assertEqual(publication["final_egress"], "SAFE")
        self.assertEqual(publication["grounding_result"], "FALLBACK")
        self.assertIsInstance(publication["text"], str)
        self.assertTrue(publication["text"])

    def test_complete_over_real_http_accepts_simulated_backend_receipt(self):
        target = service()
        target.prepare(
            prepare_request(workflow="http-simulated-regression", correlation="request-http-3")
        )
        base = self._serve(target)
        status, payload = self._post(
            base + "complete",
            complete_request(
                workflow="http-simulated-regression",
                correlation="request-http-3",
                builder=simulated_backend_canonical,
                values=(10000.0, 3.3, 10000.0, 3.3),
            ),
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "COMPLETED")
        publication = payload["publication"]
        self.assertEqual(publication["final_egress"], "SAFE")
        self.assertNotIn("observation_source_invalid", publication["text"])
        self.assertIn("simulated CH1 frequency = 10000.0", publication["text"])
        self.assertIn("simulated CH2 Vpp = 3.3", publication["text"])
        self.assertNotIn("instrument CH1 frequency", publication["text"])
        self.assertNotIn("instrument CH2 Vpp", publication["text"])


if __name__ == "__main__":
    unittest.main()
