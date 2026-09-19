import assert from "node:assert/strict";
import test from "node:test";

import type { HardwareClientPort } from "../../src/index.ts";
import type { HardwareOperation } from "../../src/generated/hardware-tools.generated.ts";
import { HarnessHardwareIpcClient } from "../../src/ipc/client.ts";
import { loadHarnessHardwareSecret } from "../../src/ipc/secret.ts";
import type { OperationScopeDecision } from "../../src/operation-scope/index.ts";
import {
  createAgentHarness,
  requestText,
  runAgent,
  textResponse,
  toolCallResponse,
  visibleToolCalls,
} from "../support/scripted-agent.ts";
import { startFakeBackend } from "../support/fake-backend-process.ts";

test("Web request grants one exact status call through authenticated FAKE IPC", { timeout: 30_000 }, async () => {
  const backend = await startFakeBackend();
  const inner = new HarnessHardwareIpcClient({
    endpoint: backend.endpoint,
    secretFile: backend.secretFile,
    loadSecret: () => loadHarnessHardwareSecret(backend.secretFile),
    connectTimeoutMs: 2_000,
    authTimeoutMs: 2_000,
    requestTimeoutMs: 5_000,
  });
  const calls: Array<{ operation: HardwareOperation; args: unknown }> = [];
  const client: HardwareClientPort = {
    start: () => inner.start(),
    dispose: () => inner.dispose(),
    invoke(operation, args, signal) {
      calls.push({ operation, args });
      return inner.invoke(operation, args, signal);
    },
  };
  const finalDecisions: OperationScopeDecision[] = [];
  const harness = await createAgentHarness({
    client,
    useProductionOperationScopeAuthority: true,
    onOperationScopeDecision(event) {
      if (event.phase === "FINAL_AUTHORIZATION") finalDecisions.push(event.decision);
    },
    config: {
      endpoint: backend.endpoint,
      secretFile: backend.secretFile,
      backendMode: "SIMULATED",
      connectTimeoutMs: 2_000,
      authTimeoutMs: 2_000,
      requestTimeoutMs: 5_000,
    },
    script: [
      toolCallResponse("web-status-first", "hardware_get_status", {}),
      (request) => {
        assert.match(requestText(request), /AIA_TEACHING_EVIDENCE_CONTEXT/);
        return toolCallResponse("web-status-reuse", "hardware_get_status", {});
      },
      textResponse("The simulated hardware status was read once; the repeated request was denied."),
    ],
  });
  try {
    await runAgent(harness.agent, "Check the current hardware status.");
    assert.deepEqual(visibleToolCalls(harness.agent).map((item) => item.name), [
      "hardware_get_status", "hardware_get_status",
    ]);
    assert.deepEqual(calls, [{ operation: "hardware.get_status", args: {} }]);
    assert.deepEqual(finalDecisions, [
      { decision: "ALLOW", reasonCode: "allowed_operation_in_scope", remainingInvocations: 0 },
    ]);
  } finally {
    await harness.ctx.fiber.dispose();
    await backend.dispose();
  }
});
