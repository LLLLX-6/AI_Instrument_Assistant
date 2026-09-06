from __future__ import annotations

from typing import Protocol

from ai_instrument_assistant.analysis.models import WaveformAnalysisResult
from ai_instrument_assistant.domain.instrument.waveform import Waveform


class WaveformAnalysisEngine(Protocol):
    """Application-facing deterministic analysis port."""

    def analyze(self, waveform: Waveform) -> WaveformAnalysisResult: ...
