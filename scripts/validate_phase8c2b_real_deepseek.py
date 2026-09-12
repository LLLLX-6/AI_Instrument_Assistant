from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
for path in (ROOT, SOURCE_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from ai_instrument_assistant.application.reasoning import TeachingGoal
from ai_instrument_assistant.application.reasoning.publication import GovernedPublicationBoundary
from ai_instrument_assistant.application.reasoning.publication.model_coordinator import (
    OneShotPublicationCoordinator,
)
from ai_instrument_assistant.application.reasoning.publication.model_runtime import (
    ModelFailureCode,
    StructuredCandidateOutcome,
    StructuredCandidateRequest,
    StructuredCandidateRuntime,
)
from ai_instrument_assistant.application.services.engineering_evidence import (
    DeterministicEngineeringComparator,
    EngineeringEvidenceAssembler,
)
from ai_instrument_assistant.application.services.engineering_evidence_workflow import (
    EngineeringEvidenceWorkflow,
)
from ai_instrument_assistant.integrations.deepseek.publication_process import (
    DeepSeekStructuredCandidateProcess,
    TypeScriptFinalEgressProcess,
)
from ai_instrument_assistant.protocol.teaching_claims import StrictCandidateParser
from tests.support.engineering_evidence_workflow import workflow_request
from tests.support.reasoning_policy import reasoning_context


PROTOCOL_ROOT = ROOT / "protocols" / "harness-publication-bridge" / "v1"
MODEL_SCRIPT = ROOT / "extensions" / "deepseek-harness" / "scripts" / "execute-structured-candidate.mjs"
EGRESS_SCRIPT = ROOT / "extensions" / "deepseek-harness" / "scripts" / "inspect-final-publication.mjs"
TEACHING_CLAIMS_ROOT = ROOT / "protocols" / "teaching-claims" / "v1"
CORRELATION_ID = "phase8c2b-real-model-validation"


class RecordingRuntime(StructuredCandidateRuntime):
    """Validation observer that cannot retry, alter, or expose candidate text."""

    def __init__(self, inner: StructuredCandidateRuntime) -> None:
        self._inner = inner
        self.outcome: StructuredCandidateOutcome | None = None
        self.generate_count = 0
        self.closed = False

    async def generate(self, request: StructuredCandidateRequest) -> StructuredCandidateOutcome:
        self.generate_count += 1
        if self.generate_count != 1:
            raise RuntimeError("one-shot validation budget exceeded")
        self.outcome = await self._inner.generate(request)
        return self.outcome

    async def aclose(self) -> None:
        try:
            await self._inner.aclose()
        finally:
            self.closed = True


def _node_executable() -> Path:
    value = shutil.which("node")
    if value is None:
        raise RuntimeError("trusted Node runtime unavailable")
    return Path(value)


def _preflight() -> dict[str, object]:
    context = reasoning_context()
    comparison_pairs = tuple(
        (item.status.value, item.reason.value)
        for item in context.comparisons
    )
    if not comparison_pairs or any(
        pair != ("INDETERMINATE", "TOLERANCE_UNSPECIFIED") for pair in comparison_pairs
    ):
        raise RuntimeError("synthetic evidence comparison semantics are outside the authorized scenario")
    workflow_result = EngineeringEvidenceWorkflow(
        assembler=EngineeringEvidenceAssembler(),
        comparator=DeterministicEngineeringComparator(),
    ).execute(workflow_request("pwm_no_tolerance"))
    cross_references = workflow_result.engineering_context.cross_references
    if not cross_references or any(
        item.state.value != "VERIFIED_LINK" for item in cross_references
    ):
        raise RuntimeError("synthetic evidence does not contain the required verified design link")
    required = (
        PROTOCOL_ROOT,
        MODEL_SCRIPT,
        EGRESS_SCRIPT,
        TEACHING_CLAIMS_ROOT,
    )
    if any(not item.exists() for item in required):
        raise RuntimeError("reviewed local runtime input is unavailable")
    harness_root = os.environ.get("DEEPSEEK_HARNESS_DEV_ROOT", "")
    if not harness_root or not (
        Path(harness_root) / "packages" / "llm" / "llm-deepseek" / "lib" / "index.js"
    ).is_file():
        raise RuntimeError("frozen Harness runtime is unavailable")
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise RuntimeError("DeepSeek credential is not configured")
    dsh_home = os.environ.get("DSH_HOME", "")
    if not dsh_home or not Path(dsh_home).is_dir():
        raise RuntimeError("trusted dedicated DSH_HOME is unavailable")
    _node_executable()
    return {
        "status": "READY",
        "scenario": "RECORDED_SYNTHETIC_PWM_OUT",
        "cross_reference": "VERIFIED_LINK",
        "comparison_count": len(comparison_pairs),
        "comparison_statuses": sorted({pair[0] for pair in comparison_pairs}),
        "comparison_reasons": sorted({pair[1] for pair in comparison_pairs}),
        "provider": "deepseek-official",
        "model": "deepseek-v4-flash",
        "tool_count": 0,
        "ipc_count": 0,
        "eda_count": 0,
        "hardware_count": 0,
    }


async def _execute_once() -> tuple[dict[str, object], str]:
    _preflight()
    node = _node_executable()
    runtime = RecordingRuntime(
        DeepSeekStructuredCandidateProcess(
            executable=node,
            script=MODEL_SCRIPT,
            protocol_root=PROTOCOL_ROOT,
            deadline_seconds=50.0,
        )
    )
    final_egress = TypeScriptFinalEgressProcess(
        executable=node,
        script=EGRESS_SCRIPT,
        protocol_root=PROTOCOL_ROOT,
    )
    boundary = GovernedPublicationBoundary(
        final_egress,
        StrictCandidateParser(TEACHING_CLAIMS_ROOT),
    )
    coordinated = await OneShotPublicationCoordinator(runtime, boundary).publish(
        context=reasoning_context(),
        goal=TeachingGoal.ASSESS_REQUIREMENT,
        correlation_id=CORRELATION_ID,
    )
    audit = coordinated.audit
    outcome = runtime.outcome
    stream_completion = (
        "STOP"
        if outcome is not None and outcome.status.value == "CANDIDATE"
        else "BOUNDED_FAILURE_NO_RAW_STREAM_EXPOSED"
    )
    candidate_valid = audit.parser_result == "PASS" and audit.grounding_result == "PASS"
    fallback_used = coordinated.publication.audit.fallback_used
    cleanup_ok = runtime.closed and audit.failure_code != ModelFailureCode.MODEL_PROCESS_FAILED.value
    valid_publication_path = (
        (not fallback_used and candidate_valid)
        or (
            fallback_used
            and audit.grounding_result == "FALLBACK"
            and coordinated.publication.status == "FALLBACK_PUBLISHED"
        )
    )
    passed = all(
        (
            audit.model_request_count == 1,
            runtime.generate_count == 1,
            audit.provider_id == "deepseek-official",
            audit.model_id == "deepseek-v4-flash",
            audit.final_egress == "SAFE",
            bool(coordinated.publication.text),
            valid_publication_path,
            audit.tool_count == 0,
            audit.ipc_count == 0,
            audit.eda_count == 0,
            audit.hardware_count == 0,
            audit.remeasurement_count == 0,
            cleanup_ok,
        )
    )
    report = {
        "validation_status": "PASS" if passed else "NOT_PASS",
        "provider_id": audit.provider_id,
        "model_id": audit.model_id,
        "model_request_count": audit.model_request_count,
        "runtime_invocation_count": audit.runtime_invocation_count,
        "stream_completion_category": stream_completion,
        "candidate_byte_count": audit.raw_byte_count,
        "candidate_digest": audit.raw_digest,
        "raw_precheck": audit.raw_precheck,
        "parser_result": audit.parser_result,
        "candidate_valid": candidate_valid,
        "selected_aliases": list(audit.selected_aliases) if candidate_valid else [],
        "grounding_result": audit.grounding_result,
        "renderer_version": audit.renderer_version,
        "final_egress_result": audit.final_egress,
        "fallback_used": fallback_used,
        "publication_status": coordinated.publication.status,
        "bounded_failure_code": audit.failure_code,
        "tool_count": audit.tool_count,
        "ipc_count": audit.ipc_count,
        "eda_count": audit.eda_count,
        "hardware_count": audit.hardware_count,
        "remeasurement_count": audit.remeasurement_count,
        "cleanup_result": "PASS" if cleanup_ok else "NOT_PASS",
    }
    return report, coordinated.publication.text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--execute-authorized-real-once", action="store_true")
    args = parser.parse_args()
    if args.preflight == args.execute_authorized_real_once:
        parser.error("select exactly one explicit validation mode")
    if args.preflight:
        print(json.dumps(_preflight(), indent=2, sort_keys=True))
        return 0
    report, publication = asyncio.run(_execute_once())
    print(json.dumps(report, indent=2, sort_keys=True))
    print("FINAL_BOUNDED_PUBLICATION_BEGIN")
    print(publication)
    print("FINAL_BOUNDED_PUBLICATION_END")
    return 0 if report["validation_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
