class JLCEDAIntegrationError(RuntimeError):
    """Base error for the JLCEDA integration boundary."""


class UnvalidatedWireDataError(JLCEDAIntegrationError):
    """A mapper was called with data not minted by SchemaValidator."""


class WireToDomainMappingError(JLCEDAIntegrationError):
    """Schema-valid wire data cannot satisfy provider-neutral domain invariants."""
