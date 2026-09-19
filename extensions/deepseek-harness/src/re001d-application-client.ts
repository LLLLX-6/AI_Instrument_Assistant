export const RE001D_APPLICATION_PROTOCOL = "aia-re001d-application/v1" as const;

export interface Re001dPrepareResponse {
  readonly protocol: typeof RE001D_APPLICATION_PROTOCOL;
  readonly operation: "prepare";
  readonly workflow_id: string;
  readonly request_correlation_id: string;
  readonly intent: "RE001D_LITE_SINGLE_POINT";
  readonly status: "CONFIRMATION_REQUIRED";
  readonly plan: Readonly<{
    /** Declared frequency target; null = no target was declared or known. */
    requested_frequency_hz: number | null;
    design_context_source: "USER_DECLARED_DESIGN_CONTEXT";
    vin: "STM32 output / CH1";
    vout: "same STM32 output / CH2";
    reference: "STM32 GND";
    operation_sequence: readonly (readonly ["hardware.measure_frequency" | "hardware.measure_vpp", 1 | 2])[];
  }>;
  readonly wiring_instructions: string;
}

export interface Re001dCompleteResponse {
  readonly protocol: typeof RE001D_APPLICATION_PROTOCOL;
  readonly operation: "complete";
  readonly workflow_id: string;
  readonly request_correlation_id: string;
  readonly status: "COMPLETED";
  readonly publication: Readonly<{
    status: string;
    text: string;
    grounding_result: "PASS" | "FALLBACK";
    final_egress: "SAFE";
    model_request_count: 0 | 1;
    model_retry_count: 0;
  }>;
}

export interface Re001dApplicationPort {
  prepare(input: Readonly<{ workflowId: string; requestCorrelationId: string; userText: string }>, signal?: AbortSignal): Promise<Re001dPrepareResponse>;
  complete(input: Readonly<{ workflowId: string; requestCorrelationId: string; governedReceipt: Readonly<Record<string, unknown>> }>, signal?: AbortSignal): Promise<Re001dCompleteResponse>;
}

export class Re001dApplicationClient implements Re001dApplicationPort {
  readonly #endpoint: URL;
  readonly #timeoutMs: number;

  constructor(endpoint = "http://127.0.0.1:49627", timeoutMs = 55_000) {
    const parsed = new URL(endpoint);
    if (parsed.protocol !== "http:" || parsed.hostname !== "127.0.0.1" || parsed.username || parsed.password) {
      throw new TypeError("RE-001D application endpoint must be loopback HTTP");
    }
    this.#endpoint = parsed;
    this.#timeoutMs = timeoutMs;
  }

  prepare(input: Readonly<{ workflowId: string; requestCorrelationId: string; userText: string }>, signal?: AbortSignal) {
    return this.#post<Re001dPrepareResponse>("prepare", {
      protocol: RE001D_APPLICATION_PROTOCOL, operation: "prepare",
      workflow_id: input.workflowId, request_correlation_id: input.requestCorrelationId,
      user_text: input.userText,
    }, signal);
  }

  complete(input: Readonly<{ workflowId: string; requestCorrelationId: string; governedReceipt: Readonly<Record<string, unknown>> }>, signal?: AbortSignal) {
    return this.#post<Re001dCompleteResponse>("complete", {
      protocol: RE001D_APPLICATION_PROTOCOL, operation: "complete",
      workflow_id: input.workflowId, request_correlation_id: input.requestCorrelationId,
      governed_receipt: input.governedReceipt,
    }, signal);
  }

  async #post<T>(operation: "prepare" | "complete", body: unknown, signal?: AbortSignal): Promise<T> {
    const timeout = AbortSignal.timeout(this.#timeoutMs);
    let response: Response;
    try {
      response = await fetch(new URL(`/aia-re001d-application/v1/${operation}`, this.#endpoint), {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify(body), signal: signal === undefined ? timeout : AbortSignal.any([signal, timeout]),
      });
    } catch {
      throw new Error("re001d_application_unavailable");
    }
    if (!response.ok) throw new Error("re001d_application_rejected");
    const text = await response.text();
    if (Buffer.byteLength(text, "utf8") > 128 * 1024) throw new Error("re001d_application_response_too_large");
    const value: unknown = JSON.parse(text);
    if (!isBoundedResponse(value, operation)) throw new Error("re001d_application_response_invalid");
    return value as T;
  }
}

function isBoundedResponse(value: unknown, operation: string): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  return item.protocol === RE001D_APPLICATION_PROTOCOL && item.operation === operation
    && typeof item.workflow_id === "string" && typeof item.request_correlation_id === "string";
}
