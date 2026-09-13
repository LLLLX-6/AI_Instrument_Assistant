from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ai_instrument_assistant.adapters.eda.in_memory import InMemoryEDAAdapter
from ai_instrument_assistant.bootstrap.interactive import compose_interactive_host
from ai_instrument_assistant.integrations.interactive import (
    InteractiveEndpointConfig,
    ProductionDesignSelectionDecisionIssuer,
)


ROOT = Path(__file__).resolve().parents[2]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--credential", type=Path, required=True)
    arguments = parser.parse_args()

    runtime = compose_interactive_host(
        repository_root=ROOT,
        eda=InMemoryEDAAdapter.for_pwm_out_scenario(),
        design_selection_issuer=ProductionDesignSelectionDecisionIssuer(),
        interactive_config=InteractiveEndpointConfig(
            port=arguments.port,
            credential_reference=arguments.credential,
        ),
    )
    runtime.host.start_workflow("Snapshot integration", "snapshot-integration")
    await runtime.start()
    print("READY", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await runtime.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
