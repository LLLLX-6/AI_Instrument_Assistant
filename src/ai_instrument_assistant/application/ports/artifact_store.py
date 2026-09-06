from __future__ import annotations

from typing import Protocol

from ai_instrument_assistant.domain.artifacts import ArtifactReference, WaveformArtifact
from ai_instrument_assistant.domain.instrument.waveform import Waveform


class ArtifactStore(Protocol):
    """Outbound port for large evidence kept outside semantic tool results."""

    def put(self, waveform: Waveform) -> WaveformArtifact: ...

    def get(self, reference: ArtifactReference) -> Waveform | None: ...
