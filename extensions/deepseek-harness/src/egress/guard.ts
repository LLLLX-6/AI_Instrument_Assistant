import type {
  EgressDiagnostic,
  EgressInspectionInput,
  EgressInspectionResult,
  EgressViolation,
  EgressViolationCategory,
} from "./models.ts";

const DEFAULT_MAXIMUM_CHARACTERS = 16_384;
const WINDOWS_DRIVE_PATH = /(?:^|[\s("'`=])(?:[A-Za-z]:[\\/])(?:[^\s<>:"|?*\r\n]+(?:[\\/]|$))+/;
const UNC_PATH = /(?:^|[\s("'`=])\\\\[^\\\s]+\\[^\\\s]+(?:\\[^\s<>:"|?*\r\n]+)*/;
const POSIX_PATH = /(?:^|[\s("'`=])\/(?:home|tmp|Users|var|etc|opt|root|workspace|mnt|srv)\/(?:[^\s\0]+\/?)+/;
const VISA_RESOURCE = /\b(?:USB\d*|TCPIP\d*|GPIB\d*|ASRL\d+)::[^\s"']+(?=$|[\s"',;)])/i;
const RAW_INSTRUMENT_COMMAND = /(?:^|[\s("'`])(?:\*[A-Z][A-Z0-9]{1,8}\??|:[A-Za-z][A-Za-z0-9]*(?::[A-Za-z][A-Za-z0-9]*)+\??)(?=$|[\s"'`,;)])/;
const SERIAL_LABEL = /\b(?:instrument[_ -]?serial|serial[_ -]?number|serial)\s*[:=]\s*["']?([A-Za-z0-9][A-Za-z0-9_-]{9,63})/i;
const ASSIGNED_CREDENTIAL = /\b(?:DEEPSEEK_API_KEY|[A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PSK)|api[_ -]?key|bearer[_ -]?token|hmac[_ -]?proof|psk)\s*[:=]\s*["']?[^\s"']{8,}/i;
const BEARER_CREDENTIAL = /\bBearer\s+[A-Za-z0-9._~+\/-]{20,}={0,2}\b/i;
const API_KEY_SHAPE = /\bsk-[A-Za-z0-9_-]{16,}\b/;
const PRIVATE_KEY_MARKER = /-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----/;
const SAMPLE_FIELD = /["']?(?:time_values|voltage_values|samples)["']?\s*[:=]\s*\[/i;
const NUMERIC_ARRAY = /\[(?:\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s*,){15,}\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?\s*\]/;

const SAFE_RESULT = Object.freeze({ status: "SAFE" } as const);

export function inspectEgressCandidate(input: EgressInspectionInput): EgressInspectionResult {
  const maximum = input.maximumCharacters ?? DEFAULT_MAXIMUM_CHARACTERS;
  if (!Number.isSafeInteger(maximum) || maximum <= 0) throw new TypeError("maximumCharacters must be a positive integer");
  const categories: EgressViolationCategory[] = [];
  if (input.candidate.length > maximum) categories.push("OVERSIZED_OUTPUT");
  if (WINDOWS_DRIVE_PATH.test(input.candidate) || UNC_PATH.test(input.candidate) || POSIX_PATH.test(input.candidate)) {
    categories.push("LOCAL_PATH");
  }
  if (VISA_RESOURCE.test(input.candidate)) categories.push("VISA_RESOURCE_IDENTIFIER");
  if (RAW_INSTRUMENT_COMMAND.test(input.candidate)) categories.push("RAW_INSTRUMENT_COMMAND");
  if (containsFullSerial(input.candidate, input.knownSensitiveValues ?? [])) categories.push("FULL_INSTRUMENT_SERIAL");
  if (ASSIGNED_CREDENTIAL.test(input.candidate)
    || BEARER_CREDENTIAL.test(input.candidate)
    || API_KEY_SHAPE.test(input.candidate)
    || PRIVATE_KEY_MARKER.test(input.candidate)) {
    categories.push("CREDENTIAL_MATERIAL");
  }
  if (SAMPLE_FIELD.test(input.candidate) || NUMERIC_ARRAY.test(input.candidate)) categories.push("WAVEFORM_SAMPLE_ARRAY");
  const unique = [...new Set(categories)];
  if (unique.length === 0) return SAFE_RESULT;
  const violations: EgressViolation[] = unique.map((category) => Object.freeze({
    category,
    source: input.source,
    correlationId: boundedCorrelation(input.correlationId),
  }));
  return Object.freeze({ status: "UNSAFE", violations: Object.freeze(violations) });
}

export function toEgressDiagnostic(violation: EgressViolation): EgressDiagnostic {
  return Object.freeze({
    status: "BLOCKED",
    category: violation.category,
    source: violation.source,
    correlationId: violation.correlationId,
  });
}

function containsFullSerial(candidate: string, knownValues: readonly string[]): boolean {
  for (const value of knownValues) {
    if (value.startsWith("***") || value.length < 5) continue;
    if (candidate.includes(value)) return true;
  }
  const labelled = SERIAL_LABEL.exec(candidate)?.[1];
  return labelled !== undefined && !labelled.startsWith("***") && /[A-Za-z]/.test(labelled) && /\d/.test(labelled);
}

function boundedCorrelation(value: string): string {
  if (typeof value !== "string" || !value.trim() || value.length > 256) return "unscoped";
  return value.trim();
}

