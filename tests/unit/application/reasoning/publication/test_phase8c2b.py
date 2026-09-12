from __future__ import annotations

import asyncio
import json
from pathlib import Path
import unittest

from ai_instrument_assistant.application.reasoning import TeachingGoal
from ai_instrument_assistant.application.reasoning.publication import (
    EgressDecision,
    GovernedPublicationBoundary,
    PublicationProjectionBuilder,
)
from ai_instrument_assistant.application.reasoning.publication.model_coordinator import (
    OneShotPublicationCoordinator,
)
from ai_instrument_assistant.application.reasoning.publication.model_runtime import (
    ModelFailureCode,
    StructuredCandidateOutcome,
)
from ai_instrument_assistant.protocol.teaching_claims import StrictCandidateParser
from tests.support.reasoning_policy import reasoning_context

ROOT = Path(__file__).resolve().parents[5]


class RecordingEgress:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def inspect(self, text: str, *, correlation_id: str) -> EgressDecision:
        self.calls.append(text)
        return EgressDecision.safe()


class FakeRuntime:
    def __init__(self, outcome: StructuredCandidateOutcome) -> None:
        self.outcome = outcome
        self.calls = 0
        self.closed = 0

    async def generate(self, request):
        self.calls += 1
        return self.outcome

    async def aclose(self) -> None:
        self.closed += 1


def candidate_for(projection) -> str:
    return json.dumps(
        {
            "schema_id": "aia-teaching-claim-candidate/v1",
            "projection_id": projection.projection_id,
            "context_fingerprint": projection.context_fingerprint,
            "envelope_id": projection.envelope_id,
            "goal": projection.goal.value,
            "ordered_permission_refs": [projection.slots[0].alias],
        },
        separators=(",", ":"),
    )


class Phase8C2BCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = reasoning_context()
        self.goal = TeachingGoal.ASSESS_REQUIREMENT
        self.egress = RecordingEgress()
        self.boundary = GovernedPublicationBoundary(
            self.egress,
            StrictCandidateParser(ROOT / "protocols" / "teaching-claims" / "v1"),
        )

    def test_valid_candidate_is_selected_once_and_published_deterministically(self) -> None:
        from ai_instrument_assistant.application.reasoning import InferenceSufficiencyEvaluator

        envelope = InferenceSufficiencyEvaluator().evaluate(self.context, self.goal)
        projection = PublicationProjectionBuilder().build(self.context, envelope, self.goal)
        runtime = FakeRuntime(StructuredCandidateOutcome.candidate(candidate_for(projection)))
        result = asyncio.run(
            OneShotPublicationCoordinator(runtime, self.boundary).publish(
                context=self.context,
                goal=self.goal,
                correlation_id="phase8c2b-valid",
            )
        )
        self.assertEqual(result.publication.status, "PUBLISHED")
        self.assertEqual(runtime.calls, 1)
        self.assertEqual(runtime.closed, 1)
        self.assertEqual(result.audit.model_request_count, 1)
        self.assertEqual(result.audit.tool_count, 0)
        self.assertEqual(result.audit.ipc_count, 0)
        self.assertEqual(result.audit.hardware_count, 0)

    def test_failed_and_cancelled_runtime_use_same_guarded_fallback_without_retry(self) -> None:
        for outcome in (
            StructuredCandidateOutcome.failed(ModelFailureCode.MODEL_PROVIDER_UNAVAILABLE),
            StructuredCandidateOutcome.cancelled(),
        ):
            with self.subTest(status=outcome.status):
                runtime = FakeRuntime(outcome)
                result = asyncio.run(
                    OneShotPublicationCoordinator(runtime, self.boundary).publish(
                        context=self.context,
                        goal=self.goal,
                        correlation_id="phase8c2b-fallback",
                    )
                )
                self.assertEqual(result.publication.status, "FALLBACK_PUBLISHED")
                self.assertEqual(runtime.calls, 1)
                self.assertEqual(runtime.closed, 1)
                self.assertTrue(result.publication.audit.fallback_used)
                self.assertEqual(result.audit.model_request_count, 1)

    def test_all_untrusted_candidate_failures_are_whole_request_fallbacks(self) -> None:
        from ai_instrument_assistant.application.reasoning import InferenceSufficiencyEvaluator

        envelope = InferenceSufficiencyEvaluator().evaluate(self.context, self.goal)
        projection = PublicationProjectionBuilder().build(self.context, envelope, self.goal)
        valid = json.loads(candidate_for(projection))
        attempts = (
            "not-json",
            json.dumps({**valid, "projection_id": "sha256:" + "9" * 64}),
            json.dumps({**valid, "ordered_permission_refs": ["p999"]}),
            json.dumps({**valid, "ordered_permission_refs": ["p001", "p001"]}),
            "x" * 16_385,
        )
        for raw in attempts:
            with self.subTest(raw=raw[:20]):
                runtime = FakeRuntime(StructuredCandidateOutcome.candidate(raw))
                result = asyncio.run(
                    OneShotPublicationCoordinator(runtime, self.boundary).publish(
                        context=self.context, goal=self.goal, correlation_id="phase8c2b-invalid",
                    )
                )
                self.assertEqual(result.publication.status, "FALLBACK_PUBLISHED")
                self.assertEqual(runtime.calls, 1)
                self.assertNotIn(raw, result.publication.text)


if __name__ == "__main__":
    unittest.main()
