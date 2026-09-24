from __future__ import annotations

from ai_instrument_assistant.application.ports.eda_interface import EDAInterfaceError


class YuanlituIntegrationError(EDAInterfaceError):
    """Bounded Yuanlitu integration failure."""


class YuanlituConnectionError(YuanlituIntegrationError):
    pass


class YuanlituProtocolError(YuanlituIntegrationError):
    pass


class YuanlituMappingError(YuanlituIntegrationError):
    pass
