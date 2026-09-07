type JsonObject = Readonly<Record<string, unknown>>;

export function renderHardwareResult(_args: unknown, value: unknown): Array<{ readonly type: "text"; readonly text: string }> {
  const root = object(value);
  if (!root) return [{ type: "text", text: "Hardware result received." }];
  const operation = text(root.operation) ?? "hardware operation";
  if (root.ok === false) {
    const error = object(root.error);
    return [{
      type: "text",
      text: `${operation} completed with hardware result ${text(error?.code) ?? "unknown_error"}: ${bounded(text(error?.message) ?? "No detail available.")}`,
    }];
  }
  const result = object(root.result);
  if (operation === "hardware.get_status") {
    const instrument = object(result?.instrument);
    const model = bounded(text(instrument?.model) ?? "unknown model", 80);
    return [{ type: "text", text: `Hardware available: ${model}.` }];
  }
  const fields: string[] = [operation];
  const quality = text(result?.quality);
  if (quality) fields.push(`quality=${bounded(quality, 32)}`);
  const observations = object(result?.observations);
  addObservation(fields, observations, "instrument_frequency", "frequency");
  addObservation(fields, observations, "software_frequency", "software_frequency");
  addObservation(fields, observations, "instrument_vpp", "Vpp");
  addDuty(fields, observations);
  const waveform = object(result?.waveform);
  const artifact = object(waveform?.artifact);
  const artifactId = text(artifact?.artifact_id);
  if (artifactId) fields.push(`waveform artifact available: ${bounded(artifactId, 80)} (opaque reference)`);
  const warnings = Array.isArray(result?.warnings)
    ? result.warnings.filter((item): item is string => typeof item === "string").slice(0, 4)
    : [];
  if (warnings.length) fields.push(`warnings=${warnings.map((item) => bounded(item, 120)).join(" | ")}`);
  return [{ type: "text", text: bounded(fields.join("; "), 1_000) }];
}

function addObservation(fields: string[], observations: JsonObject | undefined, key: string, label: string): void {
  const observation = object(observations?.[key]);
  const value = observation?.value;
  if (typeof value === "number" && Number.isFinite(value)) fields.push(`${label}=${value}`);
}

function addDuty(fields: string[], observations: JsonObject | undefined): void {
  const observation = object(observations?.software_duty_cycle);
  const duty = object(observation?.value);
  if (typeof duty?.percent === "number" && Number.isFinite(duty.percent)) fields.push(`duty=${duty.percent}%`);
}

function object(value: unknown): JsonObject | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : undefined;
}

function text(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function bounded(value: string, maximum = 256): string {
  return value.length <= maximum ? value : `${value.slice(0, maximum - 1)}…`;
}
