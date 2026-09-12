from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import threading
import unittest
import shutil
from io import BytesIO
from unittest.mock import patch
from uuid import UUID

from ai_instrument_assistant.application.reasoning import InferenceSufficiencyEvaluator, TeachingGoal
from ai_instrument_assistant.application.reasoning.publication import PublicationProjectionBuilder
from ai_instrument_assistant.application.reasoning.publication.model_runtime import (
    ModelFailureCode,
    StructuredCandidateRequest,
    StructuredCandidateStatus,
)
from ai_instrument_assistant.integrations.deepseek import DeepSeekStructuredCandidateProcess, TypeScriptFinalEgressProcess
from ai_instrument_assistant.integrations.deepseek.publication_process import _run_bounded_process
from tests.support.reasoning_policy import reasoning_context


ROOT = Path(__file__).resolve().parents[4]
PROTOCOL = ROOT / "protocols" / "harness-publication-bridge" / "v1"
CHILD = ROOT / "tests" / "support" / "phase8c2b_process_child.py"


class Cancellation:
    def __init__(self) -> None:
        self.event = threading.Event()

    def is_cancelled(self) -> bool:
        return self.event.is_set()


def request(first: str) -> StructuredCandidateRequest:
    context = reasoning_context()
    goal = TeachingGoal.ASSESS_REQUIREMENT
    envelope = InferenceSufficiencyEvaluator().evaluate(context, goal)
    projection = PublicationProjectionBuilder().build(context, envelope, goal)
    return StructuredCandidateRequest(
        UUID(first * 8 + "-1111-4111-8111-111111111111"),
        projection,
        goal,
        deadline_seconds=0.25 if first in {"2", "3"} else 5.0,
    )


class ProcessAdapterTests(unittest.TestCase):
    def adapter(self) -> DeepSeekStructuredCandidateProcess:
        return DeepSeekStructuredCandidateProcess(
            executable=Path(sys.executable), script=CHILD, protocol_root=PROTOCOL,
        )

    def test_valid_receipt_is_correlated_and_exposes_only_validated_candidate(self) -> None:
        result = asyncio.run(self.adapter().generate(request("1")))
        self.assertEqual(result.status, StructuredCandidateStatus.CANDIDATE)
        self.assertTrue(result.receipt_validated)

    def test_malformed_mismatched_digest_stderr_nonzero_and_overflow_fail_bounded(self) -> None:
        expected = {
            "4": ModelFailureCode.MODEL_PROCESS_FAILED,
            "5": ModelFailureCode.MODEL_PROCESS_FAILED,
            "6": ModelFailureCode.MODEL_RECEIPT_INVALID,
            "7": ModelFailureCode.MODEL_PROCESS_FAILED,
            "8": ModelFailureCode.MODEL_RECEIPT_INVALID,
            "9": ModelFailureCode.MODEL_RECEIPT_INVALID,
            "a": ModelFailureCode.MODEL_PROCESS_FAILED,
        }
        for mode, code in expected.items():
            with self.subTest(mode=mode):
                result = asyncio.run(self.adapter().generate(request(mode)))
                self.assertEqual(result.failure_code, code)
                self.assertIsNone(result.raw_candidate)

    def test_timeout_and_cancellation_discard_late_output_and_reap(self) -> None:
        timeout = asyncio.run(self.adapter().generate(request("2")))
        self.assertEqual(timeout.failure_code, ModelFailureCode.MODEL_REQUEST_TIMEOUT)
        cancellation = Cancellation()

        async def run_cancel():
            cancelled_request = request("3")
            cancelled_request = StructuredCandidateRequest(
                cancelled_request.request_id,
                cancelled_request.projection,
                cancelled_request.goal,
                deadline_seconds=cancelled_request.deadline_seconds,
                cancellation=cancellation,
            )
            task = asyncio.create_task(self.adapter().generate(cancelled_request))
            await asyncio.sleep(0.05)
            cancellation.event.set()
            return await task

        cancelled = asyncio.run(run_cancel())
        self.assertEqual(cancelled.status, StructuredCandidateStatus.CANCELLED)
        self.assertIsNone(cancelled.raw_candidate)

    def test_independent_final_egress_process_has_no_model_credential(self) -> None:
        node = shutil.which("node")
        self.assertIsNotNone(node)
        inspector = TypeScriptFinalEgressProcess(
            executable=Path(node or "node"),
            script=ROOT / "extensions/deepseek-harness/scripts/inspect-final-publication.mjs",
            protocol_root=PROTOCOL,
        )
        self.assertEqual(inspector.inspect("Bounded output.", correlation_id="phase8c2b").status.value, "SAFE")
        blocked = inspector.inspect("DEEPSEEK_API_KEY=sk-SYNTHETIC_TEST_VALUE_0000", correlation_id="phase8c2b")
        self.assertEqual(blocked.status.value, "UNSAFE")

    def test_terminate_failure_still_attempts_kill_and_bounded_reap(self) -> None:
        class FakeProcess:
            def __init__(self) -> None:
                self.stdin = BytesIO()
                self.stdout = BytesIO()
                self.stderr = BytesIO()
                self.returncode = None
                self.killed = False

            def poll(self):
                return self.returncode

            def terminate(self):
                raise OSError("synthetic cleanup failure")

            def wait(self, timeout=None):
                if not self.killed:
                    import subprocess
                    raise subprocess.TimeoutExpired("synthetic", timeout)
                self.returncode = 9
                return 9

            def kill(self):
                self.killed = True

        fake = FakeProcess()
        with patch("ai_instrument_assistant.integrations.deepseek.publication_process.subprocess.Popen", return_value=fake):
            result = _run_bounded_process(("fixed", "fixed"), b"{}\n", {}, 0.01, 32, None)
        self.assertTrue(result.timed_out)
        self.assertTrue(fake.killed)
        self.assertEqual(fake.returncode, 9)


if __name__ == "__main__":
    unittest.main()
