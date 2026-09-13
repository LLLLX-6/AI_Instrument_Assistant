from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path

from .protocol import INTERACTIVE_PROTOCOL


DEFAULT_INTERACTIVE_PORT = 49626
RESERVED_PRODUCT_PORTS = frozenset({49624, 49625})


@dataclass(frozen=True, slots=True)
class InteractiveEndpointConfig:
    """Host-owned product configuration; the port is not protocol identity."""

    bind_host: str = "127.0.0.1"
    port: int = DEFAULT_INTERACTIVE_PORT
    protocol_version: str = INTERACTIVE_PROTOCOL
    credential_reference: Path | None = field(default=None, repr=False)
    lifecycle_ownership: str = "application_host"

    def __post_init__(self) -> None:
        if self.bind_host != "127.0.0.1":
            raise ValueError("interactive endpoint must bind explicit 127.0.0.1")
        if not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("interactive endpoint port must be valid")
        if self.port in RESERVED_PRODUCT_PORTS:
            raise ValueError("interactive endpoint collides with a reserved product port")
        if self.protocol_version != INTERACTIVE_PROTOCOL:
            raise ValueError("interactive endpoint protocol version is fixed")
        if self.lifecycle_ownership != "application_host":
            raise ValueError("interactive endpoint lifecycle must be Host-owned")
        if self.credential_reference is not None:
            object.__setattr__(self, "credential_reference", Path(self.credential_reference))

    def load_credential(self) -> bytes:
        if self.credential_reference is None:
            raise ValueError("interactive credential reference is not configured")
        encoded = self.credential_reference.read_text(encoding="ascii").strip()
        if len(encoded) != 43:
            raise ValueError("interactive credential must be a 32-byte base64url secret")
        try:
            value = base64.urlsafe_b64decode(encoded + "=")
        except (ValueError, UnicodeError) as error:
            raise ValueError("interactive credential is malformed") from error
        if len(value) != 32:
            raise ValueError("interactive credential must decode to 32 bytes")
        return value


# Compatibility name for Phase 8.5A callers. Its semantics now reflect the
# reviewed separate-listener decision rather than the rejected 49624 path plan.
LoopbackGatewayConfig = InteractiveEndpointConfig
