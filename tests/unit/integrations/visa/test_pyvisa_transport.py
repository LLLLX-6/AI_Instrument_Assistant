from __future__ import annotations

import unittest

from ai_instrument_assistant.hardware.errors import (
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
)
from ai_instrument_assistant.integrations.visa.pyvisa_transport import PyVisaTransport


class Resource:
    def __init__(self) -> None:
        self.timeout = None
        self.write_termination = None
        self.closed = False

    def write(self, value: str) -> None: pass
    def query(self, value: str) -> str: return value
    def read_raw(self) -> bytes: return b""
    def close(self) -> None: self.closed = True


class ResourceManager:
    def __init__(self, resource: object | None = None) -> None:
        self.resource = resource or Resource()
        self.opened: list[str] = []

    def list_resources(self, query: str) -> tuple[str, ...]:
        self.query = query
        return ("USB0::0x1AB1::0x04CE::SERIAL::INSTR",)

    def open_resource(self, name: str) -> object:
        self.opened.append(name)
        return self.resource


class ConfigurationFailingResource:
    def __init__(self) -> None:
        self.closed = False

    @property
    def timeout(self) -> None:
        return None

    @timeout.setter
    def timeout(self, value: int) -> None:
        raise OSError("configuration failed")

    def close(self) -> None:
        self.closed = True


class VisaTimeout(Exception):
    error_code = -1073807339


class PyVisaTransportTests(unittest.TestCase):
    def test_discovery_and_open_keep_pyvisa_resource_behind_boundary(self) -> None:
        manager = ResourceManager()
        transport = PyVisaTransport(resource_manager=manager)

        self.assertEqual(
            ("USB0::0x1AB1::0x04CE::SERIAL::INSTR",),
            transport.discover_resources(),
        )
        connection = transport.open(
            "USB0::0x1AB1::0x04CE::SERIAL::INSTR", timeout_seconds=2.5
        )
        self.assertEqual(2500, manager.resource.timeout)
        self.assertEqual("\n", manager.resource.write_termination)
        self.assertFalse(hasattr(connection, "resource"))
        connection.close()
        self.assertTrue(manager.resource.closed)
        connection.close()
        with self.assertRaises(TransportDisconnectedError):
            connection.write(":RUN")
        with self.assertRaises(TransportDisconnectedError):
            connection.query("*IDN?")
        with self.assertRaises(TransportDisconnectedError):
            connection.read_raw()

    def test_open_validates_arguments_before_opening_resource(self) -> None:
        manager = ResourceManager()
        transport = PyVisaTransport(resource_manager=manager)
        for resource_name, timeout in (
            ("", 1.0), ("USB::SCOPE", 0.0), ("USB::SCOPE", -1.0),
            ("USB::SCOPE", float("nan")), ("USB::SCOPE", float("inf")),
        ):
            with self.subTest(resource_name=resource_name, timeout=timeout):
                with self.assertRaises(ValueError):
                    transport.open(resource_name, timeout_seconds=timeout)
        self.assertEqual([], manager.opened)

    def test_partially_opened_resource_is_closed_when_configuration_fails(self) -> None:
        resource = ConfigurationFailingResource()
        manager = ResourceManager(resource)
        transport = PyVisaTransport(resource_manager=manager)
        with self.assertRaises(TransportError):
            transport.open("USB::SCOPE", timeout_seconds=1.0)
        self.assertTrue(resource.closed)

    def test_backend_errors_are_classified_without_leaking_backend_details(self) -> None:
        class FailingManager(ResourceManager):
            def __init__(self, error: Exception) -> None:
                super().__init__()
                self.error = error

            def open_resource(self, name: str) -> object:
                raise self.error

        cases = (
            (VisaTimeout("private VISA detail"), TransportTimeoutError),
            (ConnectionError("private VISA detail"), TransportDisconnectedError),
            (OSError("private VISA detail"), TransportError),
        )
        for source_error, expected_type in cases:
            transport = PyVisaTransport(resource_manager=FailingManager(source_error))
            with self.subTest(error=type(source_error).__name__):
                with self.assertRaises(expected_type) as raised:
                    transport.open("USB::SCOPE", timeout_seconds=1.0)
                self.assertNotIn("private VISA detail", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
