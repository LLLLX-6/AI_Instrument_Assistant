from __future__ import annotations

import asyncio
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any

from .service import (
    PROTOCOL,
    RE001DApplicationError,
    RE001DApplicationService,
    _plain,
)


MAXIMUM_BODY_BYTES = 128 * 1024
PATHS = {
    "/aia-re001d-application/v1/prepare": "prepare",
    "/aia-re001d-application/v1/complete": "complete",
}


def _encode_json(value: object) -> bytes:
    """Encode a private-protocol value for the HTTP wire.

    The application service returns frozen immutable structures (the schema
    validator freezes dicts into MappingProxyType and lists into tuples).
    `_plain` — the protocol's existing recursive converter and the exact
    inverse of `_freeze_json` — maps them to JSON-compatible plain values.
    Unknown non-protocol objects fail closed: json.dumps raises TypeError and
    they are never coerced with str().
    """
    return json.dumps(_plain(value), separators=(",", ":"), sort_keys=True).encode("utf-8")


def create_server(service: RE001DApplicationService, port: int = 49627) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
            operation = PATHS.get(self.path)
            if operation is None:
                self._reply(HTTPStatus.NOT_FOUND, _error("INVALID_REQUEST"))
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAXIMUM_BODY_BYTES:
                    raise RE001DApplicationError("INVALID_REQUEST")
                value = json.loads(self.rfile.read(length))
                result = (
                    service.prepare(value)
                    if operation == "prepare"
                    else asyncio.run(service.complete(value))
                )
            except RE001DApplicationError as error:
                self._reply(HTTPStatus.BAD_REQUEST, _error(error.code))
                return
            except Exception:
                self._reply(HTTPStatus.BAD_REQUEST, _error("INVALID_REQUEST"))
                return
            try:
                self._reply(HTTPStatus.OK, result)
            except Exception:
                # The request was valid; the transport failed to encode the
                # response. That is a server-side failure, not an invalid
                # request, so the existing internal-failure code is used.
                self._reply(HTTPStatus.BAD_REQUEST, _error("APPLICATION_FAILURE"))

        def log_message(self, format: str, *args: Any) -> None:
            return None

        def _reply(self, status: HTTPStatus, value: object) -> None:
            body = _encode_json(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def _error(code: str) -> dict[str, str]:
    allowed = {
        "INVALID_REQUEST", "UNSUPPORTED_INTENT", "CORRELATION_MISMATCH",
        "DUPLICATE_COMPLETE", "APPLICATION_FAILURE",
    }
    return {"protocol": PROTOCOL, "status": "FAILED", "error_code": code if code in allowed else "APPLICATION_FAILURE"}
