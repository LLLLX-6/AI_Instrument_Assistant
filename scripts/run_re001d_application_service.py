from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
for value in (ROOT, ROOT / "src"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from ai_instrument_assistant.application.reasoning.publication import (  # noqa: E402
    GovernedPublicationBoundary,
    OneShotPublicationCoordinator,
)
from ai_instrument_assistant.integrations.deepseek.publication_process import (  # noqa: E402
    DeepSeekStructuredCandidateProcess,
    TypeScriptFinalEgressProcess,
)
from ai_instrument_assistant.integrations.re001d_application import RE001DApplicationService  # noqa: E402
from ai_instrument_assistant.integrations.re001d_application.http_server import create_server  # noqa: E402
from ai_instrument_assistant.protocol.teaching_claims import StrictCandidateParser  # noqa: E402


def publisher() -> OneShotPublicationCoordinator:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("trusted Node runtime unavailable")
    protocol = ROOT / "protocols/harness-publication-bridge/v1"
    runtime = DeepSeekStructuredCandidateProcess(
        executable=Path(node),
        script=ROOT / "extensions/deepseek-harness/scripts/execute-structured-candidate.mjs",
        protocol_root=protocol,
    )
    boundary = GovernedPublicationBoundary(
        TypeScriptFinalEgressProcess(
            executable=Path(node),
            script=ROOT / "extensions/deepseek-harness/scripts/inspect-final-publication.mjs",
            protocol_root=protocol,
        ),
        StrictCandidateParser(ROOT / "protocols/teaching-claims/v1"),
    )
    return OneShotPublicationCoordinator(runtime, boundary)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=49627)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    service = RE001DApplicationService(ROOT / "protocols/re001d-application/v1", publisher)
    server = create_server(service, args.port)
    print(f"RE-001D application service READY on 127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
