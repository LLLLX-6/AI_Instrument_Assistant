from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_instrument_assistant.integrations.yuanlitu.client import YuanlituStdioMcpClient
from ai_instrument_assistant.integrations.yuanlitu.composition import compose_yuanlitu_eda_provider
from ai_instrument_assistant.integrations.yuanlitu.errors import YuanlituProtocolError


class FakeStdout:
    def __init__(self, messages: list[object]) -> None:
        self.messages = [json.dumps(item).encode() + b"\n" for item in messages]

    async def readline(self) -> bytes:
        return self.messages.pop(0)


class FakeStdin:
    def __init__(self) -> None:
        self.writes: list[dict[str, object]] = []

    def write(self, value: bytes) -> None:
        self.writes.append(json.loads(value))

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None


class FakeProcess:
    def __init__(self) -> None:
        self.stdin = FakeStdin()
        self.stdout = FakeStdout([
            {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "yuanlitu-mcp-service", "version": "0.1.1"}}},
            {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "must-not-be-parsed"}], "structuredContent": {"bounded": True}}},
        ])
        self.returncode = None

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = 0

    async def wait(self) -> int:
        self.returncode = 0
        return 0


class YuanlituClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_uses_structured_content_and_static_tool_name(self) -> None:
        process = FakeProcess()
        with patch("asyncio.create_subprocess_exec", return_value=process):
            client = YuanlituStdioMcpClient(Path(sys.executable))
            await client.start()
            result = await client.call_tool("easyeda_health", {})
            await client.close()
        self.assertEqual({"bounded": True}, result)
        self.assertEqual("initialize", process.stdin.writes[0]["method"])
        self.assertEqual("notifications/initialized", process.stdin.writes[1]["method"])
        self.assertEqual("tools/call", process.stdin.writes[2]["method"])
        self.assertEqual("easyeda_health", process.stdin.writes[2]["params"]["name"])

    async def test_unknown_or_mutating_tool_is_rejected_before_process_access(self) -> None:
        client = YuanlituStdioMcpClient(Path(sys.executable))
        with self.assertRaises(YuanlituProtocolError):
            await client.call_tool("schematic_apply_operations", {})

    def test_narrow_composition_selects_yuanlitu_adapter(self) -> None:
        runtime = compose_yuanlitu_eda_provider(Path(sys.executable))
        self.assertIs(runtime.adapter._client, runtime.client)


if __name__ == "__main__":
    unittest.main()
