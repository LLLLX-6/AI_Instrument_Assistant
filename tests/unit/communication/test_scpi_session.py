from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import Event

from ai_instrument_assistant.hardware.errors import (
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
)
from ai_instrument_assistant.communication.scpi_session import ScpiSession
from tests.support.recorded_visa import RecordedVisaConnection


class ScpiSessionTests(unittest.TestCase):
    def test_write_query_and_close_delegate_without_instrument_semantics(self) -> None:
        connection = RecordedVisaConnection(responses={"*IDN?": "RIGOL,MODEL,SN,FW\n"})
        session = ScpiSession(connection)

        session.write(":RUN")
        self.assertEqual("RIGOL,MODEL,SN,FW", session.query("*IDN?"))
        session.close()

        self.assertEqual(("write", ":RUN"), connection.calls[0])
        self.assertEqual(("query", "*IDN?"), connection.calls[1])
        self.assertTrue(connection.closed)

    def test_timeout_and_disconnect_are_transport_errors_without_backend_text(self) -> None:
        for backend_error, expected in (
            (TimeoutError("backend secret detail"), TransportTimeoutError),
            (ConnectionError("usb serial secret"), TransportDisconnectedError),
            (OSError("driver secret"), TransportError),
        ):
            with self.subTest(expected=expected.__name__):
                session = ScpiSession(RecordedVisaConnection(query_error=backend_error))
                with self.assertRaises(expected) as caught:
                    session.query("*IDN?")
                self.assertNotIn("secret", str(caught.exception))

    def test_closed_session_rejects_io(self) -> None:
        session = ScpiSession(RecordedVisaConnection())
        session.close()
        with self.assertRaises(TransportDisconnectedError):
            session.write(":RUN")

    def test_binary_read_is_unmodified_and_type_checked(self) -> None:
        connection = RecordedVisaConnection(raw_response=b"#13\x00\x0a\xff")
        session = ScpiSession(connection)
        self.assertEqual(b"#13\x00\x0a\xff", session.read_raw())
        self.assertEqual([("read_raw", "")], connection.calls)

        connection.raw_response = "not-bytes"  # type: ignore[assignment]
        with self.assertRaises(TransportError):
            session.read_raw()

    def test_one_scpi_exchange_blocks_interleaving_io(self) -> None:
        query_started = Event()
        release_query = Event()

        class BlockingConnection(RecordedVisaConnection):
            def query(self, command: str) -> str:
                query_started.set()
                if not release_query.wait(timeout=2.0):
                    raise TimeoutError("test synchronization timeout")
                return super().query(command)

        connection = BlockingConnection(responses={"*IDN?": "RIGOL,MODEL,SN,FW"})
        session = ScpiSession(connection)
        with ThreadPoolExecutor(max_workers=2) as executor:
            query = executor.submit(session.query, "*IDN?")
            self.assertTrue(query_started.wait(timeout=1.0))
            write = executor.submit(session.write, ":STOP")
            try:
                with self.assertRaises(FutureTimeoutError):
                    write.result(timeout=0.05)
            finally:
                release_query.set()
            self.assertEqual("RIGOL,MODEL,SN,FW", query.result(timeout=1.0))
            write.result(timeout=1.0)

        self.assertEqual([("query", "*IDN?"), ("write", ":STOP")], connection.calls)


if __name__ == "__main__":
    unittest.main()
