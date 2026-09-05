class JLCEDAIntegrationError(RuntimeError):
    """Base error for the JLCEDA integration boundary."""


class UnvalidatedWireDataError(JLCEDAIntegrationError):
    """A mapper was called with data not minted by SchemaValidator."""


class WireToDomainMappingError(JLCEDAIntegrationError):
    """Schema-valid wire data cannot satisfy provider-neutral domain invariants."""


class JLCEDATransportUnavailableError(JLCEDAIntegrationError):
    """No authenticated JLCEDA transport session is available."""


class JLCEDARequestTimeoutError(JLCEDAIntegrationError):
    """A JLCEDA request exceeded its response deadline."""


class JLCEDAConnectionLostError(JLCEDAIntegrationError):
    """The JLCEDA connection disappeared while a request was pending."""


class JLCEDAProtocolError(JLCEDAIntegrationError):
    """A JLCEDA message violated schema, session, or correlation semantics."""
