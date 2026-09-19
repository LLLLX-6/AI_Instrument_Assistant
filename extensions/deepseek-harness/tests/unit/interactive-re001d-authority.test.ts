import assert from "node:assert/strict";
import test from "node:test";
import { createUserMessage } from "@deepseek-ai/dsh-llm";

import type { Re001dApplicationPort } from "../../src/re001d-application-client.ts";
import {
  InteractiveRe001dAuthority,
  RE001D_WEB_CONFIRMATION,
  RE001D_WEB_REQUEST,
} from "../../src/interactive-re001d-authority.ts";

function agent(id = "workflow-1"): any { return { id, session: { id: id + "-session" }, followup() {} }; }
function message(text: string, id = "request-1"): any {
  return { ...createUserMessage({ content: [{ type: "text", text }], source: { kind: "user" } }), id };
}
function application(): Re001dApplicationPort & { prepareCount: number; completeCount: number; receipt?: any } {
  return {
    prepareCount: 0, completeCount: 0,
    async prepare(input) {
      this.prepareCount += 1;
      return {
        protocol: "aia-re001d-application/v1", operation: "prepare",
        workflow_id: input.workflowId, request_correlation_id: input.requestCorrelationId,
        intent: "RE001D_LITE_SINGLE_POINT", status: "CONFIRMATION_REQUIRED",
        plan: {
          requested_frequency_hz: null, design_context_source: "USER_DECLARED_DESIGN_CONTEXT",
          vin: "STM32 output / CH1", vout: "same STM32 output / CH2", reference: "STM32 GND",
          operation_sequence: [
            ["hardware.measure_frequency", 1], ["hardware.measure_vpp", 1],
            ["hardware.measure_frequency", 2], ["hardware.measure_vpp", 2],
          ],
        }, wiring_instructions: "Confirm safe wiring.",
      };
    },
    async complete(input) {
      this.completeCount += 1; this.receipt = input.governedReceipt;
      return {
        protocol: "aia-re001d-application/v1", operation: "complete",
        workflow_id: input.workflowId, request_correlation_id: input.requestCorrelationId,
        status: "COMPLETED", publication: {
          status: "FALLBACK_PUBLISHED", text: "Grounded simulated result.",
          grounding_result: "FALLBACK", final_egress: "SAFE", model_request_count: 0, model_retry_count: 0,
        },
      };
    },
  };
}

test("prepare has no authority and explicit confirmation unlocks four exact scopes", async () => {
  const app = application(); const authority = new InteractiveRe001dAuthority(app); const subject = agent();
  assert.equal(await authority.claim(subject, message(RE001D_WEB_REQUEST)), "PREPARED");
  assert.equal(authority.snapshot(subject)?.issuedScopeCount, 0);
  assert.equal(authority.snapshot(subject)?.physicalConfirmationCount, 0);
  assert.equal(authority.resolve(subject, "hardware.measure_frequency", { channel: 1 }), undefined);
  assert.equal(await authority.claim(subject, message(RE001D_WEB_CONFIRMATION, "confirmation-event")), "CONFIRMED");
  assert.equal(authority.snapshot(subject)?.issuedScopeCount, 4);
  assert.equal(authority.snapshot(subject)?.physicalConfirmationCount, 2);
  assert.equal(authority.resolve(subject, "hardware.measure_frequency", { channel: 2 }), undefined);
  const first = authority.resolve(subject, "hardware.measure_frequency", { channel: 1 });
  assert.equal(first?.scope.targetChannel, 1);
  assert.equal(first?.scope.allowedOperations[0]?.maxInvocations, 1);
  assert.equal(first?.requestCorrelationId, "request-1");
  assert.equal(authority.policy(subject, "hardware.measure_frequency", { channel: 1 }, "REAL")?.confirmation?.channel, 1);
});

test("fixed order completes once and passes canonical results without copying numbers", async () => {
  const app = application(); const authority = new InteractiveRe001dAuthority(app); const subject = agent();
  await authority.claim(subject, message(RE001D_WEB_REQUEST));
  await authority.claim(subject, message(RE001D_WEB_CONFIRMATION, "confirmation-event"));
  const order = [["hardware.measure_frequency", 1], ["hardware.measure_vpp", 1], ["hardware.measure_frequency", 2], ["hardware.measure_vpp", 2]] as const;
  let publication;
  for (const [operation, channel] of order) {
    const context = authority.resolve(subject, operation, { channel });
    assert.deepEqual(context?.scope.allowedOperations, [{ operation, maxInvocations: 1 }]);
    assert.equal(context?.scope.targetChannel, channel);
    assert.equal(context?.workflowId, "workflow-1");
    assert.equal(context?.requestCorrelationId, "request-1");
    const policy = authority.policy(subject, operation, { channel }, "REAL");
    assert.equal(policy?.confirmation?.scope.workflowId, "workflow-1");
    assert.equal(policy?.confirmation?.scope.requestCorrelationId, "request-1");
    publication = await authority.recordSuccess(subject, operation, { channel }, { opaque: `${operation}:${channel}` });
  }
  assert.equal(app.completeCount, 1);
  assert.equal(app.receipt.operations.length, 4);
  assert.equal(publication?.content[0]?.type, "text");
  assert.equal(authority.snapshot(subject), undefined);
});

test("new request, wrong workflow, wrong operation, and failure revoke or deny authority", async () => {
  const app = application(); const authority = new InteractiveRe001dAuthority(app); const subject = agent();
  await authority.claim(subject, message(RE001D_WEB_REQUEST));
  await authority.claim(subject, message(RE001D_WEB_CONFIRMATION, "confirmation-event"));
  assert.equal(authority.resolve(agent("wrong"), "hardware.measure_frequency", { channel: 1 }), undefined);
  assert.equal(authority.resolve(subject, "hardware.measure_vpp", { channel: 1 }), undefined);
  authority.recordFailure(subject);
  assert.equal(authority.resolve(subject, "hardware.measure_frequency", { channel: 1 }), undefined);
  await authority.claim(subject, message("Measure frequency on CH1", "new-request"));
  assert.equal(authority.snapshot(subject), undefined);
});

test("an altered confirmation revokes preparation and cannot be replayed", async () => {
  const authority = new InteractiveRe001dAuthority(application());
  const subject = agent();
  assert.equal(await authority.claim(subject, message(RE001D_WEB_REQUEST)), "PREPARED");
  assert.equal(await authority.claim(subject, message(`${RE001D_WEB_CONFIRMATION} extra`, "wrong-confirmation")), "IGNORED");
  assert.equal(authority.snapshot(subject), undefined);
  assert.equal(await authority.claim(subject, message(RE001D_WEB_CONFIRMATION, "late-confirmation")), "IGNORED");
  assert.equal(authority.resolve(subject, "hardware.measure_frequency", { channel: 1 }), undefined);
});

test("generic affirmatives never authorize and revoke the prepared workflow", async () => {
  const authority = new InteractiveRe001dAuthority(application());
  const subject = agent();
  assert.equal(await authority.claim(subject, message(RE001D_WEB_REQUEST)), "PREPARED");
  for (const [index, text] of ["yes", "confirm", "confirmed", "I confirm", "确认", "已确认安全，请开始测量"].entries()) {
    assert.equal(await authority.claim(subject, message(text, `generic-${index}`)), "IGNORED");
  }
  assert.equal(authority.snapshot(subject), undefined);
  assert.equal(authority.resolve(subject, "hardware.measure_frequency", { channel: 1 }), undefined);
});

test("a failed workflow cannot be revived by the exact confirmation phrase", async () => {
  const authority = new InteractiveRe001dAuthority(application());
  const subject = agent();
  await authority.claim(subject, message(RE001D_WEB_REQUEST));
  await authority.claim(subject, message(RE001D_WEB_CONFIRMATION, "confirmation-event"));
  authority.recordFailure(subject);
  assert.equal(await authority.claim(subject, message(RE001D_WEB_CONFIRMATION, "reconfirmation")), "REJECTED");
  assert.equal(authority.resolve(subject, "hardware.measure_frequency", { channel: 1 }), undefined);
});
