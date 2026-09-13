from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from ai_instrument_assistant.application.interactive import (
    ApplicationHost,
    DesignSelectionDecisionIssuer,
    FrontendKind,
    OperationAuthorizationIssuer,
    PhysicalConfirmationIssuer,
)
from ai_instrument_assistant.application.ports.eda_interface import EDAInterface
from ai_instrument_assistant.integrations.interactive import (
    InteractiveEndpointConfig,
    InteractiveGateway,
    InteractiveProtocolBinding,
    InteractiveWebSocketServer,
    InteractiveWireProjector,
    ProductionDesignSelectionDecisionIssuer,
    ProductionInteractiveApplicationActions,
)
from ai_instrument_assistant.integrations.jlceda.mapper import JLCEDADomainMapper
from ai_instrument_assistant.integrations.jlceda.remote_adapter import JLCEDARemoteAdapter
from ai_instrument_assistant.integrations.jlceda.transport.gateway import LocalWebSocketGateway
from ai_instrument_assistant.integrations.jlceda.transport.state_machine import ProtocolStateMachine
from ai_instrument_assistant.protocol.schema_registry import SchemaRegistry
from ai_instrument_assistant.protocol.schema_validator import SchemaValidator


class _TransportAuthenticatedOnly:
    """Reject the legacy direct-credential gateway entry in production composition."""

    def authenticate(self, frontend_kind: FrontendKind, credential: str) -> None:
        del frontend_kind, credential
        return None


@dataclass(slots=True)
class InteractiveHostRuntime:
    """Minimal production lifecycle for the provider and interactive listeners."""

    host: ApplicationHost
    actions: ProductionInteractiveApplicationActions
    gateway: InteractiveGateway
    interactive_server: InteractiveWebSocketServer
    provider_gateway: LocalWebSocketGateway | None = None
    provider_port: int = 49624
    _started: bool = False

    @property
    def interactive_uri(self) -> str:
        return self.interactive_server.uri

    async def start(self) -> None:
        if self._started:
            return
        if self.provider_gateway is not None:
            await self.provider_gateway.start(port=self.provider_port)
        try:
            await self.interactive_server.start()
        except BaseException:
            if self.provider_gateway is not None:
                await self.provider_gateway.stop()
            raise
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            await self.interactive_server.stop()
        finally:
            try:
                if self.provider_gateway is not None:
                    await self.provider_gateway.stop()
            finally:
                await self.host.shutdown()
                self._started = False


def compose_interactive_host(
    *,
    repository_root: Path,
    eda: EDAInterface,
    design_selection_issuer: DesignSelectionDecisionIssuer,
    interactive_config: InteractiveEndpointConfig,
    operation_authorization_issuer: OperationAuthorizationIssuer | None = None,
    physical_confirmation_issuer: PhysicalConfirmationIssuer | None = None,
    provider_gateway: LocalWebSocketGateway | None = None,
    provider_port: int = 49624,
) -> InteractiveHostRuntime:
    """Production glue; tests may replace only the outbound EDA Port."""
    root = Path(repository_root).resolve()
    protocol = InteractiveProtocolBinding.from_repository(root)
    host = ApplicationHost(
        design_selection_issuer=design_selection_issuer,
        operation_authorization_issuer=operation_authorization_issuer,
        physical_confirmation_issuer=physical_confirmation_issuer,
    )
    actions = ProductionInteractiveApplicationActions(host=host, eda=eda)
    gateway = InteractiveGateway(
        host=host,
        protocol=protocol,
        authenticator=_TransportAuthenticatedOnly(),
        actions=actions,
    )
    server = InteractiveWebSocketServer(
        config=interactive_config,
        gateway=gateway,
        projector=InteractiveWireProjector(host, protocol),
    )
    return InteractiveHostRuntime(
        host=host,
        actions=actions,
        gateway=gateway,
        interactive_server=server,
        provider_gateway=provider_gateway,
        provider_port=provider_port,
    )


def compose_jlceda_interactive_host(
    *,
    repository_root: Path,
    interactive_config: InteractiveEndpointConfig,
    provider_credential_reference: Path,
    provider_port: int = 49624,
) -> InteractiveHostRuntime:
    """Real JLCEDA provider plus interactive Host production composition."""
    if provider_port != 49624:
        if provider_port in {49625, interactive_config.port}:
            raise ValueError("provider endpoint collides with another authority domain")
        if not 1 <= provider_port <= 65535:
            raise ValueError("provider port must be valid")
    root = Path(repository_root).resolve()
    provider_validator = SchemaValidator(
        SchemaRegistry.from_directory(root / "protocols" / "jlceda" / "v1")
    )
    provider_gateway = LocalWebSocketGateway(
        validator=provider_validator,
        state_machine=ProtocolStateMachine(
            secret=_load_secret(provider_credential_reference)
        ),
    )
    eda = JLCEDARemoteAdapter(
        request_client=provider_gateway,
        validator=provider_validator,
        mapper=JLCEDADomainMapper(),
    )
    return compose_interactive_host(
        repository_root=root,
        eda=eda,
        design_selection_issuer=ProductionDesignSelectionDecisionIssuer(),
        interactive_config=interactive_config,
        provider_gateway=provider_gateway,
        provider_port=provider_port,
    )


def _load_secret(path: Path) -> bytes:
    encoded = Path(path).read_text(encoding="ascii").strip()
    if len(encoded) != 43:
        raise ValueError("provider credential must be a 32-byte base64url secret")
    try:
        value = base64.urlsafe_b64decode(encoded + "=")
    except (ValueError, UnicodeError) as error:
        raise ValueError("provider credential is malformed") from error
    if len(value) != 32:
        raise ValueError("provider credential must decode to 32 bytes")
    return value
