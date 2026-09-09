export type DeliveryState = "NOT_SENT" | "SENT_UNCONFIRMED" | "RESPONSE_RECEIVED";

export type AdapterFailureCode =
  | "invalid_tool_arguments"
  | "operation_scope_denied"
  | "policy_confirmation_required"
  | "policy_denied"
  | "ipc_authentication_failed"
  | "backend_protocol_mismatch"
  | "backend_unreachable"
  | "backend_response_invalid"
  | "indeterminate_execution"
  | "request_timeout"
  | "client_cancelled_wait";

const SAFE_MESSAGES: Readonly<Record<AdapterFailureCode, string>> = {
  invalid_tool_arguments: "Hardware tool arguments are invalid.",
  operation_scope_denied: "Hardware operation is outside the trusted request scope.",
  policy_confirmation_required: "Physical setup confirmation is required before this hardware measurement.",
  policy_denied: "Hardware tool request was denied by policy.",
  ipc_authentication_failed: "Hardware backend authentication failed.",
  backend_protocol_mismatch: "Hardware backend protocol is incompatible.",
  backend_unreachable: "Hardware backend is unavailable.",
  backend_response_invalid: "Hardware backend returned an invalid response.",
  indeterminate_execution: "Hardware request outcome is indeterminate; it was not replayed.",
  request_timeout: "Hardware request timed out before delivery.",
  client_cancelled_wait: "The caller stopped waiting; physical execution was not reported as cancelled.",
};

export class AdapterFailure extends Error {
  readonly code: AdapterFailureCode;
  readonly deliveryState: DeliveryState;

  constructor(
    code: AdapterFailureCode,
    message: string = SAFE_MESSAGES[code],
    deliveryState: DeliveryState = "NOT_SENT",
  ) {
    super(message);
    this.name = "HarnessHardwareAdapterFailure";
    this.code = code;
    this.deliveryState = deliveryState;
  }
}

export function safeAdapterFailure(
  code: AdapterFailureCode,
  deliveryState: DeliveryState = "NOT_SENT",
): AdapterFailure {
  return new AdapterFailure(code, SAFE_MESSAGES[code], deliveryState);
}
