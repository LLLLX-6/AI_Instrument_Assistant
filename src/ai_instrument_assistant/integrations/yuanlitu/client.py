from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import YuanlituConnectionError, YuanlituProtocolError


ALLOWED_READ_TOOLS = frozenset({
    "easyeda_health",
    "schematic_list_pages",
    "schematic_inspect_page",
})
EXPECTED_SERVER_NAME = "yuanlitu-mcp-service"
EXPECTED_SERVER_VERSION = "0.1.1"


class YuanlituStdioMcpClient:
    """Minimal, sequential stdio client for three fixed Yuanlitu read tools."""

    def __init__(
        self,
        executable: Path,
        *,
        startup_timeout: float = 20.0,
        call_timeout: float = 120.0,
    ) -> None:
        self._executable = Path(executable).resolve()
        if not self._executable.is_file():
            raise ValueError("Yuanlitu executable does not exist")
        if startup_timeout <= 0 or call_timeout <= 0:
            raise ValueError("timeouts must be positive")
        self._startup_timeout = startup_timeout
        self._call_timeout = call_timeout
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._process is not None:
            return
        try:
            process = await asyncio.create_subprocess_exec(
                str(self._executable),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=4 * 1024 * 1024,
            )
        except OSError as error:
            raise YuanlituConnectionError("Yuanlitu process could not be started") from error
        self._process = process
        try:
            response = await self._request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "ai-instrument-assistant", "version": "0.2"},
                },
                timeout=self._startup_timeout,
            )
            result = _mapping(response.get("result"), "initialize.result")
            server = _mapping(result.get("serverInfo"), "initialize.serverInfo")
            if server.get("name") != EXPECTED_SERVER_NAME or server.get("version") != EXPECTED_SERVER_VERSION:
                raise YuanlituProtocolError("unsupported Yuanlitu server identity")
            await self._notify("notifications/initialized", {})
        except BaseException:
            await self.close()
            raise

    async def call_tool(self, name: str, arguments: object) -> object:
        if name not in ALLOWED_READ_TOOLS:
            raise YuanlituProtocolError("tool is outside the fixed read-only allowlist")
        if not isinstance(arguments, Mapping):
            raise YuanlituProtocolError("tool arguments must be an object")
        response = await self._request(
            "tools/call", {"name": name, "arguments": dict(arguments)}, timeout=self._call_timeout
        )
        result = _mapping(response.get("result"), "tools.call.result")
        if result.get("isError") is True:
            raise YuanlituProtocolError("Yuanlitu read tool reported a bounded failure")
        return dict(_mapping(result.get("structuredContent"), "tools.call.structuredContent"))

    async def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 2.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def _request(self, method: str, params: object, *, timeout: float) -> Mapping[str, Any]:
        async with self._lock:
            process = self._require_process()
            request_id = self._next_id
            self._next_id += 1
            await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout)
            except asyncio.TimeoutError as error:
                raise YuanlituConnectionError("Yuanlitu request timed out") from error
            if not line:
                raise YuanlituConnectionError("Yuanlitu process closed its response stream")
            response = _json_mapping(line)
            if response.get("jsonrpc") != "2.0" or response.get("id") != request_id:
                raise YuanlituProtocolError("Yuanlitu response correlation failed")
            if "error" in response:
                raise YuanlituProtocolError("Yuanlitu returned a JSON-RPC error")
            return response

    async def _notify(self, method: str, params: object) -> None:
        async with self._lock:
            await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def _write(self, message: object) -> None:
        process = self._require_process()
        assert process.stdin is not None
        process.stdin.write(json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n")
        try:
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as error:
            raise YuanlituConnectionError("Yuanlitu request stream is unavailable") from error

    def _require_process(self) -> asyncio.subprocess.Process:
        process = self._process
        if process is None or process.stdin is None or process.stdout is None or process.returncode is not None:
            raise YuanlituConnectionError("Yuanlitu client is not running")
        return process


def _json_mapping(line: bytes) -> Mapping[str, Any]:
    if len(line) > 4 * 1024 * 1024:
        raise YuanlituProtocolError("Yuanlitu response exceeds the bounded size")
    try:
        value = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise YuanlituProtocolError("Yuanlitu response is not valid JSON") from error
    return _mapping(value, "JSON-RPC response")


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise YuanlituProtocolError(f"{name} must be an object")
    return value
