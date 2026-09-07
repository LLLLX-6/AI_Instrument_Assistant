export const STATUS_RESULT = {
  contract_version: "1.0",
  ok: true,
  operation: "hardware.get_status",
  result: {
    instrument: {
      manufacturer: "RIGOL TECHNOLOGIES",
      model: "DS1102Z-E",
      serial_number: "***9517",
      firmware_version: "00.06.03.SP2",
    },
    observed_at: "2026-09-07T08:00:00Z",
  },
} as const;

export const HARDWARE_ERROR_RESULT = {
  contract_version: "1.0",
  ok: false,
  operation: "hardware.measure_vpp",
  error: {
    code: "measurement_failed",
    message: "Measurement could not be completed.",
    details: {},
  },
} as const;

export const DEGRADED_PWM_RESULT = {
  contract_version: "1.0",
  ok: true,
  operation: "hardware.measure_pwm",
  result: {
    request_id: "550e8400-e29b-41d4-a716-446655440000",
    kind: "pwm",
    channel: 1,
    context_id: "PWM_OUT",
    instrument: {
      manufacturer: "RIGOL TECHNOLOGIES",
      model: "DS1102Z-E",
      serial_number: "***9517",
      firmware_version: "00.06.03.SP2",
    },
    waveform: {
      artifact: {
        artifact_id: "550e8400-e29b-41d4-a716-446655440001",
        uri: "memory://waveforms/550e8400-e29b-41d4-a716-446655440001",
        media_type: "application/vnd.aia.waveform+json",
        size_bytes: 1200,
      },
      channel: 1,
      point_count: 1200,
      sample_interval_seconds: 2e-7,
      time_range_seconds: [-0.00012, 0.0001198],
      voltage_range_v: [-0.34, 0.008],
      acquisition_mode: "normal",
      captured_at: "2026-09-07T08:00:00Z",
    },
    observations: {},
    quality: "degraded",
    warnings: ["Only bounded evidence is available."],
    coherence: {
      software_observations: "same_artifact",
      instrument_vs_software: "sequential_same_session",
    },
    provenance: {
      started_at: "2026-09-07T08:00:00Z",
      completed_at: "2026-09-07T08:00:01Z",
      analysis_algorithm: { name: "aia.threshold_edges", version: "1.0.0" },
    },
  },
} as const;
