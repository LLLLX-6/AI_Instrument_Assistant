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

const INSTRUMENT = {
  manufacturer: "AIA SIMULATOR",
  model: "SimulatedOscilloscope",
  serial_number: "***SIM1",
  firmware_version: "sim-1.0",
} as const;

const ARTIFACT_ID = "550e8400-e29b-41d4-a716-446655440001";

function observation(
  value: unknown,
  source: "instrument" | "software_analysis" | "simulated",
  method: string,
  quality: "good" | "degraded" | "unavailable" = "good",
  warnings: readonly string[] = [],
) {
  return {
    value,
    source,
    method,
    observed_at: "2026-09-08T09:00:00Z",
    quality,
    warnings,
    evidence_artifact_ids: source === "software_analysis" ? [ARTIFACT_ID] : [],
  };
}

function measurement(
  operation: "hardware.measure_frequency" | "hardware.measure_vpp" | "hardware.capture_waveform" | "hardware.measure_pwm",
  kind: "frequency" | "vpp" | "waveform" | "pwm",
  observations: Readonly<Record<string, unknown>>,
  waveform: unknown = null,
) {
  return {
    contract_version: "1.0",
    ok: true,
    operation,
    result: {
      request_id: "550e8400-e29b-41d4-a716-446655440000",
      kind,
      channel: 1,
      context_id: null,
      instrument: INSTRUMENT,
      waveform,
      observations,
      quality: "good",
      warnings: [],
      coherence: {
        software_observations: waveform === null ? "unknown" : "same_artifact",
        instrument_vs_software: "unknown",
      },
      provenance: {
        started_at: "2026-09-08T09:00:00Z",
        completed_at: "2026-09-08T09:00:01Z",
        analysis_algorithm: null,
      },
    },
  } as const;
}

export const SIMULATED_FREQUENCY_RESULT = measurement(
  "hardware.measure_frequency",
  "frequency",
  { instrument_frequency: observation(10_000, "simulated", "deterministic simulation") },
);

export const SIMULATED_VPP_RESULT = measurement(
  "hardware.measure_vpp",
  "vpp",
  { instrument_vpp: observation(3.3, "simulated", "deterministic simulation") },
);

export const SIMULATED_WAVEFORM_RESULT = measurement(
  "hardware.capture_waveform",
  "waveform",
  {},
  {
    artifact: {
      artifact_id: ARTIFACT_ID,
      uri: `memory://waveforms/${ARTIFACT_ID}`,
      media_type: "application/vnd.aia.waveform+json",
      size_bytes: 1200,
    },
    channel: 1,
    point_count: 1200,
    sample_interval_seconds: 2e-7,
    time_range_seconds: [-0.00012, 0.0001198],
    voltage_range_v: [0, 3.3],
    acquisition_mode: "normal",
    captured_at: "2026-09-08T09:00:00Z",
  },
);

export const SIMULATED_PWM_RESULT = {
  ...measurement(
    "hardware.measure_pwm",
    "pwm",
    {
      instrument_frequency: observation(10_000, "simulated", "deterministic simulation"),
      instrument_vpp: observation(3.3, "simulated", "deterministic simulation"),
      software_frequency: observation(10_000, "software_analysis", "threshold edges"),
      software_duty_cycle: observation(
        { ratio: 0.3, percent: 30 }, "software_analysis", "threshold edges",
      ),
    },
    SIMULATED_WAVEFORM_RESULT.result.waveform,
  ),
  result: {
    ...measurement(
      "hardware.measure_pwm",
      "pwm",
      {
        instrument_frequency: observation(10_000, "simulated", "deterministic simulation"),
        instrument_vpp: observation(3.3, "simulated", "deterministic simulation"),
        software_frequency: observation(10_000, "software_analysis", "threshold edges"),
        software_duty_cycle: observation(
          { ratio: 0.3, percent: 30 }, "software_analysis", "threshold edges",
        ),
      },
      SIMULATED_WAVEFORM_RESULT.result.waveform,
    ).result,
    context_id: "PWM_OUT",
    coherence: {
      software_observations: "same_artifact",
      instrument_vs_software: "sequential_same_session",
    },
    provenance: {
      started_at: "2026-09-08T09:00:00Z",
      completed_at: "2026-09-08T09:00:01Z",
      analysis_algorithm: { name: "aia.threshold_edges", version: "1.0.0" },
    },
  },
} as const;

export const PARTIAL_PWM_RESULT = {
  ...SIMULATED_PWM_RESULT,
  result: {
    ...SIMULATED_PWM_RESULT.result,
    quality: "degraded",
    warnings: ["Instrument frequency unavailable; software estimate remains available."],
    observations: {
      instrument_frequency: observation(
        null, "instrument", "oscilloscope query", "unavailable", ["No stable trigger."],
      ),
      software_frequency: observation(10_002, "software_analysis", "threshold edges", "degraded"),
    },
  },
} as const;

export const HARDWARE_UNAVAILABLE_RESULT = {
  contract_version: "1.0",
  ok: false,
  operation: "hardware.measure_vpp",
  error: {
    code: "hardware_unavailable",
    message: "Hardware backend is unavailable.",
    details: {},
  },
} as const;
