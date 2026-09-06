from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from ai_instrument_assistant.domain.artifacts import ArtifactReference, WaveformArtifact
from ai_instrument_assistant.domain.instrument.waveform import Waveform


class InMemoryArtifactStore:
    """Development store; references are process-local and non-durable."""

    def __init__(self, *, id_factory: Callable[[], UUID] = uuid4) -> None:
        self._id_factory = id_factory
        self._waveforms: dict[UUID, Waveform] = {}

    def put(self, waveform: Waveform) -> WaveformArtifact:
        if not isinstance(waveform, Waveform):
            raise TypeError("waveform must be a Waveform")
        artifact_id = self._id_factory()
        if not isinstance(artifact_id, UUID):
            raise TypeError("id_factory must return UUID")
        if artifact_id in self._waveforms:
            raise ValueError("artifact identifier already exists")
        self._waveforms[artifact_id] = waveform
        return WaveformArtifact(
            reference=ArtifactReference(
                artifact_id=artifact_id,
                uri=f"memory://waveforms/{artifact_id}",
                media_type="application/vnd.aia.waveform",
            ),
            channel=waveform.channel,
            point_count=waveform.point_count,
            sample_interval_seconds=waveform.sample_interval_seconds,
            time_start_seconds=waveform.time_values[0],
            time_end_seconds=waveform.time_values[-1],
            minimum_voltage=min(waveform.voltage_values),
            maximum_voltage=max(waveform.voltage_values),
            acquisition_mode=waveform.acquisition_mode.value,
            captured_at=waveform.captured_at,
        )

    def get(self, reference: ArtifactReference) -> Waveform | None:
        if not isinstance(reference, ArtifactReference):
            raise TypeError("reference must be an ArtifactReference")
        return self._waveforms.get(reference.artifact_id)
