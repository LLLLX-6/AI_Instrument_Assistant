from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity


class InstrumentModelTests(unittest.TestCase):
    def test_identity_is_finite_immutable_provenance(self) -> None:
        identity = InstrumentIdentity(
            manufacturer="RIGOL TECHNOLOGIES",
            model="DS1102Z-E",
            serial_number="DS1ZA000000000",
            firmware_version="00.06.02",
            raw_identity="RIGOL TECHNOLOGIES,DS1102Z-E,DS1ZA000000000,00.06.02",
        )
        self.assertEqual("DS1102Z-E", identity.model)
        self.assertTrue(identity.raw_identity.startswith("RIGOL TECHNOLOGIES"))
        with self.assertRaises(FrozenInstanceError):
            identity.model = "other"  # type: ignore[misc]

    def test_identity_rejects_blank_fields(self) -> None:
        with self.assertRaises(ValueError):
            InstrumentIdentity("RIGOL", "", "SN", "FW")

    def test_identity_rejects_unbounded_or_control_text(self) -> None:
        for serial in ("X" * 257, "serial\nforged"):
            with self.subTest(serial=serial[:20]), self.assertRaises(ValueError):
                InstrumentIdentity("RIGOL", "MODEL", serial, "FW")


if __name__ == "__main__":
    unittest.main()
