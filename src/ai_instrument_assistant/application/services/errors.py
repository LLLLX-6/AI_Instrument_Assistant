class MeasurementServiceError(RuntimeError):
    """Base error for bounded application workflow failures."""


class AnalysisFailedError(MeasurementServiceError):
    """A waveform could not be analyzed into semantic observations."""


class ArtifactUnavailableError(MeasurementServiceError):
    """Evidence could not be stored or referenced."""
