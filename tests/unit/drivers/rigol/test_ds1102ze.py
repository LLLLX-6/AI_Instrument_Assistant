from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import Event

from ai_instrument_assistant.application.ports.oscilloscope import (
    ChannelCoupling,
    OscilloscopeInterface,
)
from ai_instrument_assistant.drivers.rigol.ds1102ze import DS1102ZEDriver
from ai_instrument_assistant.hardware.errors import (
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDisconnectedError,
    InstrumentIdentityMismatchError,
    InstrumentResponseError,
    InstrumentStateVerificationError,
    InstrumentTimeoutError,
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
)
from tests.support.recorded_visa import RecordedVisaConnection, RecordedVisaTransport


RESOURCE = "USB0::0x1AB1::0x04CE::DS1ZA000000000::INSTR"
IDN = "RIGOL TECHNOLOGIES,DS1102Z-E,DS1ZA000000000,00.06.02"


def driver(
    responses: dict[str, str] | None = None,
    *,
    connect: bool = True,
    operation_error: Exception | None = None,
) -> tuple[DS1102ZEDriver, RecordedVisaConnection, RecordedVisaTransport]:
    connection = RecordedVisaConnection(responses={"*IDN?": IDN, **(responses or {})})
    transport = RecordedVisaTransport(connection)
    scope = DS1102ZEDriver(transport, RESOURCE, timeout_seconds=2.0)
    if connect:
        scope.connect()
        connection.calls.clear()
        connection.query_error = operation_error
    return scope, connection, transport


class DS1102ZEDriverTests(unittest.TestCase):
    def test_driver_implements_provider_neutral_sync_port(self) -> None:
        scope, _, _ = driver(connect=False)
        self.assertIsInstance(scope, OscilloscopeInterface)

    def test_connect_opens_resource_validates_and_preserves_raw_identity(self) -> None:
        scope, connection, transport = driver()
        identity = scope.get_identity()
        self.assertEqual("RIGOL TECHNOLOGIES", identity.manufacturer)
        self.assertEqual("DS1102Z-E", identity.model)
        self.assertEqual("DS1ZA000000000", identity.serial_number)
        self.assertEqual("00.06.02", identity.firmware_version)
        self.assertEqual(IDN, identity.raw_identity)
        self.assertEqual([(RESOURCE, 2.0)], transport.open_calls)
        self.assertEqual([], connection.calls)

    def test_connect_is_idempotent_and_disconnect_is_safe_twice(self) -> None:
        scope, connection, transport = driver()
        scope.connect()
        self.assertEqual(1, len(transport.open_calls))
        scope.disconnect()
        scope.disconnect()
        self.assertTrue(connection.closed)
        with self.assertRaises(InstrumentDisconnectedError):
            scope.get_identity()

    def test_valid_operation_before_connect_is_rejected_without_transport_io(self) -> None:
        scope, connection, transport = driver(connect=False)
        with self.assertRaises(InstrumentDisconnectedError):
            scope.get_channel_enabled(1)
        self.assertEqual([], connection.calls)
        self.assertEqual([], transport.open_calls)

    def test_wrong_model_or_manufacturer_is_identity_mismatch_and_closes(self) -> None:
        for response in (
            "RIGOL TECHNOLOGIES,DS1202Z-E,SN,FW",
            "OTHER,DS1102Z-E,SN,FW",
        ):
            connection = RecordedVisaConnection(responses={"*IDN?": response})
            scope = DS1102ZEDriver(
                RecordedVisaTransport(connection), RESOURCE, timeout_seconds=2.0
            )
            with self.subTest(response=response), self.assertRaises(
                InstrumentIdentityMismatchError
            ):
                scope.connect()
            self.assertTrue(connection.closed)

    def test_malformed_identity_is_response_error_and_closes(self) -> None:
        connection = RecordedVisaConnection(responses={"*IDN?": "RIGOL,DS1102Z-E,SN"})
        scope = DS1102ZEDriver(
            RecordedVisaTransport(connection), RESOURCE, timeout_seconds=2.0
        )
        with self.assertRaises(InstrumentResponseError):
            scope.connect()
        self.assertTrue(connection.closed)

    def test_connect_maps_timeout_and_disconnect_without_backend_text(self) -> None:
        cases = (
            (TransportTimeoutError("private"), InstrumentTimeoutError),
            (TransportDisconnectedError("private"), InstrumentDisconnectedError),
            (TransportError("private"), InstrumentConnectionError),
        )
        for source_error, expected_type in cases:
            transport = RecordedVisaTransport(
                RecordedVisaConnection(), open_error=source_error
            )
            scope = DS1102ZEDriver(transport, RESOURCE, timeout_seconds=2.0)
            with self.subTest(error=type(source_error).__name__):
                with self.assertRaises(expected_type) as raised:
                    scope.connect()
                self.assertNotIn("private", str(raised.exception))

    def test_channel_and_timebase_getters_emit_only_audited_queries(self) -> None:
        scope, connection, _ = driver({
            ":CHANnel1:DISPlay?": "1",
            ":CHANnel1:COUPling?": "DC",
            ":CHANnel1:PROBe?": "1.000000e+01",
            ":CHANnel1:UNITs?": "VOLT",
            ":CHANnel1:SCALe?": "1.000000e+00",
            ":TIMebase:MODE?": "MAIN",
            ":TIMebase:MAIN:SCALe?": "2.000000e-05",
        })
        self.assertTrue(scope.get_channel_enabled(1))
        self.assertIs(ChannelCoupling.DC, scope.get_channel_coupling(1))
        self.assertEqual(10.0, scope.get_probe_ratio(1))
        self.assertEqual(1.0, scope.get_channel_scale(1))
        self.assertEqual(20e-6, scope.get_timebase_scale())
        self.assertEqual([
            ("query", ":CHANnel1:DISPlay?"),
            ("query", ":CHANnel1:COUPling?"),
            ("query", ":CHANnel1:PROBe?"),
            ("query", ":CHANnel1:UNITs?"),
            ("query", ":CHANnel1:SCALe?"),
            ("query", ":TIMebase:MODE?"),
            ("query", ":TIMebase:MAIN:SCALe?"),
        ], connection.calls)

    def test_individual_setters_write_then_verify_readback(self) -> None:
        scope, connection, _ = driver({
            ":CHANnel1:DISPlay?": "1",
            ":CHANnel1:COUPling?": "DC",
            ":CHANnel1:PROBe?": "10.0000000001",
            ":CHANnel1:UNITs?": "VOLT",
            ":CHANnel1:VERNier?": "0",
            ":CHANnel1:SCALe?": "1.0000000001",
            ":TIMebase:MODE?": "MAIN",
            ":TIMebase:MAIN:SCALe?": "2.0000000001e-05",
        })
        scope.set_channel_enabled(1, True)
        scope.set_channel_coupling(1, ChannelCoupling.DC)
        scope.set_probe_ratio(1, 10.0)
        scope.set_channel_scale(1, 1.0)
        scope.set_timebase_scale(20e-6)
        self.assertEqual([
            ("write", ":CHANnel1:DISPlay ON"),
            ("query", ":CHANnel1:DISPlay?"),
            ("write", ":CHANnel1:COUPling DC"),
            ("query", ":CHANnel1:COUPling?"),
            ("write", ":CHANnel1:PROBe 10"),
            ("query", ":CHANnel1:PROBe?"),
            ("query", ":CHANnel1:UNITs?"),
            ("query", ":CHANnel1:VERNier?"),
            ("query", ":CHANnel1:PROBe?"),
            ("write", ":CHANnel1:SCALe 1"),
            ("query", ":CHANnel1:SCALe?"),
            ("query", ":TIMebase:MODE?"),
            ("write", ":TIMebase:MAIN:SCALe 2e-05"),
            ("query", ":TIMebase:MAIN:SCALe?"),
        ], connection.calls)
        self.assertFalse(any("SYSTem:ERRor" in command for _, command in connection.calls))

    def test_all_channel_methods_reject_zero_and_three_before_scpi(self) -> None:
        operations = (
            lambda scope, channel: scope.get_channel_enabled(channel),
            lambda scope, channel: scope.set_channel_enabled(channel, True),
            lambda scope, channel: scope.get_channel_coupling(channel),
            lambda scope, channel: scope.set_channel_coupling(channel, ChannelCoupling.DC),
            lambda scope, channel: scope.get_channel_scale(channel),
            lambda scope, channel: scope.set_channel_scale(channel, 1.0),
            lambda scope, channel: scope.get_probe_ratio(channel),
            lambda scope, channel: scope.set_probe_ratio(channel, 10.0),
            lambda scope, channel: scope.measure_frequency(channel),
            lambda scope, channel: scope.measure_vpp(channel),
        )
        for operation in operations:
            for channel in (0, 3):
                scope, connection, transport = driver(connect=False)
                with self.subTest(operation=operation, channel=channel), self.assertRaises(ValueError):
                    operation(scope, channel)
                self.assertEqual([], connection.calls)
                self.assertEqual([], transport.open_calls)

    def test_invalid_local_values_reject_before_scpi(self) -> None:
        operations = (
            lambda scope: scope.set_channel_enabled(1, 1),
            lambda scope: scope.set_channel_coupling(1, "DC"),
            lambda scope: scope.set_probe_ratio(1, 3.0),
            lambda scope: scope.set_channel_scale(1, float("nan")),
            lambda scope: scope.set_timebase_scale(3e-9),
        )
        for operation in operations:
            scope, connection, transport = driver(connect=False)
            with self.subTest(operation=operation), self.assertRaises((TypeError, ValueError)):
                operation(scope)
            self.assertEqual([], connection.calls)
            self.assertEqual([], transport.open_calls)

    def test_each_setter_reports_state_verification_mismatch(self) -> None:
        cases = (
            ({":CHANnel1:DISPlay?": "0"}, lambda scope: scope.set_channel_enabled(1, True)),
            ({":CHANnel1:COUPling?": "AC"}, lambda scope: scope.set_channel_coupling(1, ChannelCoupling.DC)),
            ({":CHANnel1:PROBe?": "1"}, lambda scope: scope.set_probe_ratio(1, 10.0)),
            ({
                ":CHANnel1:UNITs?": "VOLT", ":CHANnel1:VERNier?": "0",
                ":CHANnel1:PROBe?": "10", ":CHANnel1:SCALe?": "2",
            }, lambda scope: scope.set_channel_scale(1, 1.0)),
            ({":TIMebase:MODE?": "MAIN", ":TIMebase:MAIN:SCALe?": "5e-05"},
             lambda scope: scope.set_timebase_scale(20e-6)),
        )
        for responses, operation in cases:
            scope, _, _ = driver(responses)
            with self.subTest(responses=responses), self.assertRaises(
                InstrumentStateVerificationError
            ):
                operation(scope)

    def test_non_voltage_scale_and_non_main_timebase_are_explicit_state_failures(self) -> None:
        scope, _, _ = driver({":CHANnel1:UNITs?": "WATT"})
        with self.assertRaises(InstrumentStateVerificationError):
            scope.get_channel_scale(1)
        scope, _, _ = driver({":TIMebase:MODE?": "ROLL"})
        with self.assertRaises(InstrumentStateVerificationError):
            scope.get_timebase_scale()

    def test_measurements_accept_numeric_and_scientific_notation(self) -> None:
        scope, connection, _ = driver({
            ":MEASure:ITEM? FREQuency,CHANnel1": "10000",
            ":MEASure:ITEM? VPP,CHANnel1": "3.280000e+00",
        })
        self.assertEqual(10_000.0, scope.measure_frequency(1))
        self.assertEqual(3.28, scope.measure_vpp(1))
        self.assertEqual([
            ("query", ":MEASure:ITEM? FREQuency,CHANnel1"),
            ("query", ":MEASure:ITEM? VPP,CHANnel1"),
        ], connection.calls)

    def test_malformed_nonfinite_overflow_and_negative_measurements_are_rejected(self) -> None:
        for value in ("", "not-a-number", "nan", "inf", "1e999", "-1"):
            for command, operation in (
                (":MEASure:ITEM? FREQuency,CHANnel1", lambda scope: scope.measure_frequency(1)),
                (":MEASure:ITEM? VPP,CHANnel1", lambda scope: scope.measure_vpp(1)),
            ):
                scope, _, _ = driver({command: value})
                with self.subTest(value=value, command=command), self.assertRaises(
                    InstrumentResponseError
                ):
                    operation(scope)

    def test_observed_unavailable_frequency_sentinel_is_rejected(self) -> None:
        scope, _, _ = driver({
            ":MEASure:ITEM? FREQuency,CHANnel1": "9.9e37"
        })
        with self.assertRaises(InstrumentResponseError):
            scope.measure_frequency(1)

    def test_disconnected_mid_operation_is_mapped_without_backend_details(self) -> None:
        scope, _, _ = driver(
            {":CHANnel1:DISPlay?": "1"},
            operation_error=TransportDisconnectedError("private VISA detail"),
        )
        with self.assertRaises(InstrumentDisconnectedError) as raised:
            scope.get_channel_enabled(1)
        self.assertNotIn("private VISA detail", str(raised.exception))

    def test_driver_operation_lock_keeps_set_and_readback_atomic(self) -> None:
        entered_readback = Event()
        release_readback = Event()

        class BlockingConnection(RecordedVisaConnection):
            def query(self, command: str) -> str:
                if command == ":CHANnel1:DISPlay?":
                    entered_readback.set()
                    if not release_readback.wait(timeout=2.0):
                        raise TimeoutError("test synchronization timeout")
                return super().query(command)

        connection = BlockingConnection(responses={
            "*IDN?": IDN,
            ":CHANnel1:DISPlay?": "1",
            ":MEASure:ITEM? VPP,CHANnel1": "3.3",
        })
        scope = DS1102ZEDriver(
            RecordedVisaTransport(connection), RESOURCE, timeout_seconds=2.0
        )
        scope.connect()
        connection.calls.clear()
        with ThreadPoolExecutor(max_workers=2) as executor:
            setting = executor.submit(scope.set_channel_enabled, 1, True)
            self.assertTrue(entered_readback.wait(timeout=1.0))
            measurement = executor.submit(scope.measure_vpp, 1)
            try:
                with self.assertRaises(FutureTimeoutError):
                    measurement.result(timeout=0.05)
            finally:
                release_readback.set()
            setting.result(timeout=1.0)
            self.assertEqual(3.3, measurement.result(timeout=1.0))
        self.assertEqual(("query", ":MEASure:ITEM? VPP,CHANnel1"), connection.calls[-1])

    def test_identity_failure_remains_primary_when_cleanup_also_fails(self) -> None:
        connection = RecordedVisaConnection(
            responses={"*IDN?": "RIGOL TECHNOLOGIES,DS1202Z-E,SN,FW"},
            close_error=TransportError("close failed"),
        )
        scope = DS1102ZEDriver(
            RecordedVisaTransport(connection), RESOURCE, timeout_seconds=2.0
        )
        with self.assertRaises(InstrumentIdentityMismatchError):
            scope.connect()


if __name__ == "__main__":
    unittest.main()
