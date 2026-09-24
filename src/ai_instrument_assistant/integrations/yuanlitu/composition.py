from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .adapter import YuanlituMcpEDAAdapter
from .client import YuanlituStdioMcpClient


@dataclass(frozen=True, slots=True)
class YuanlituEDAProviderRuntime:
    client: YuanlituStdioMcpClient
    adapter: YuanlituMcpEDAAdapter

    async def start(self) -> None:
        await self.client.start()

    async def stop(self) -> None:
        await self.client.close()


def compose_yuanlitu_eda_provider(executable: Path) -> YuanlituEDAProviderRuntime:
    client = YuanlituStdioMcpClient(executable)
    return YuanlituEDAProviderRuntime(client=client, adapter=YuanlituMcpEDAAdapter(client))
