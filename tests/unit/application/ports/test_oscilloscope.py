from __future__ import annotations

import inspect
import unittest

from ai_instrument_assistant.application.ports.oscilloscope import OscilloscopeInterface


class OscilloscopeInterfaceTests(unittest.TestCase):
    def test_phase6b_port_is_sync_and_exposes_only_semantic_operations(self) -> None:
        expected = {
            "connect", "disconnect", "get_identity",
            "get_channel_enabled", "set_channel_enabled",
            "get_channel_coupling", "set_channel_coupling",
            "get_channel_scale", "set_channel_scale",
            "get_probe_ratio", "set_probe_ratio",
            "get_timebase_scale", "set_timebase_scale",
            "measure_frequency", "measure_vpp",
        }
        public = {
            name for name, value in inspect.getmembers(OscilloscopeInterface)
            if callable(value) and not name.startswith("_")
        }
        self.assertEqual(expected, public)
        for name in expected:
            self.assertFalse(inspect.iscoroutinefunction(getattr(OscilloscopeInterface, name)))

    def test_port_contains_no_raw_scpi_or_waveform_escape_hatch(self) -> None:
        names = set(dir(OscilloscopeInterface))
        self.assertNotIn("send_scpi", names)
        self.assertNotIn("capture_waveform", names)
        self.assertNotIn("query", names)


if __name__ == "__main__":
    unittest.main()
