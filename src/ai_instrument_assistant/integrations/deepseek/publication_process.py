from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Mapping
from uuid import uuid4

from ai_instrument_assistant.application.reasoning.publication.model_runtime import (
    CancellationHandle,
    ModelFailureCode,
    StructuredCandidateOutcome,
    StructuredCandidateRequest,
)
from ai_instrument_assistant.application.reasoning.publication.models import EgressDecision
from ai_instrument_assistant.protocol.harness_publication_bridge import (
    HarnessPublicationBridge,
    PrivateBridgeError,
    encode_one_json_line,
    parse_one_json_line,
)


MODEL_STDIN_LIMIT = 96 * 1024
MODEL_STDOUT_LIMIT = 128 * 1024
EGRESS_STDIN_LIMIT = 20 * 1024
EGRESS_STDOUT_LIMIT = 8 * 1024
STDERR_LIMIT = 4 * 1024
REAP_GRACE_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class _ProcessResult:
    stdout: bytes
    returncode: int
    stderr_count: int
    timed_out: bool
    cancelled: bool
    overflowed: bool


class DeepSeekStructuredCandidateProcess:
    def __init__(
        self,
        *,
        executable: Path,
        script: Path,
        protocol_root: Path,
        trusted_environment: Mapping[str, str] | None = None,
        deadline_seconds: float = 50.0,
    ) -> None:
        self._command = _fixed_command(executable, script)
        self._bridge = HarnessPublicationBridge(protocol_root)
        self._environment = _allowlisted_environment(trusted_environment or os.environ, model=True)
        self._deadline = min(deadline_seconds, 50.0)

    async def generate(
        self,
        request: StructuredCandidateRequest,
    ) -> StructuredCandidateOutcome:
        wire = self._bridge.build_model_request(str(request.request_id), request.projection.model_payload())
        encoded = encode_one_json_line(wire, MODEL_STDIN_LIMIT)
        result = await asyncio.to_thread(
            _run_bounded_process,
            self._command,
            encoded,
            self._environment,
            min(request.deadline_seconds, self._deadline),
            MODEL_STDOUT_LIMIT,
            request.cancellation,
        )
        if result.cancelled:
            return StructuredCandidateOutcome.cancelled(model_request_count=1)
        if result.timed_out:
            return StructuredCandidateOutcome.failed(ModelFailureCode.MODEL_REQUEST_TIMEOUT)
        if result.overflowed or result.stderr_count > 0 or result.returncode != 0:
            return StructuredCandidateOutcome.failed(ModelFailureCode.MODEL_PROCESS_FAILED)
        try:
            value = parse_one_json_line(result.stdout, MODEL_STDOUT_LIMIT)
            receipt = self._bridge.parse_model_receipt(
                value,
                expected_request_id=wire["request_id"],
                expected_request_digest=wire["request_digest"],
            )
        except PrivateBridgeError:
            return StructuredCandidateOutcome.failed(ModelFailureCode.MODEL_RECEIPT_INVALID)
        metadata = {
            "request_digest": receipt.request_digest,
            "executor_version": receipt.executor_version,
            "runtime_version": receipt.runtime_version,
            "provider_id": receipt.provider_id,
            "model_id": receipt.model_id,
            "model_request_count": receipt.model_request_count,
            "raw_digest": receipt.raw_digest,
            "raw_precheck": receipt.raw_precheck,
            "receipt_validated": True,
        }
        if receipt.status == "CANDIDATE":
            return StructuredCandidateOutcome.candidate(receipt.raw_candidate or "", **metadata)
        try:
            code = ModelFailureCode(receipt.failure_code or "MODEL_PROCESS_FAILED")
        except ValueError:
            code = ModelFailureCode.MODEL_RECEIPT_INVALID
        if receipt.status == "CANCELLED":
            return StructuredCandidateOutcome.cancelled(**metadata)
        return StructuredCandidateOutcome.failed(code, **metadata)

    async def aclose(self) -> None:
        return None


class TypeScriptFinalEgressProcess:
    """Synchronous port required by 8C.2A; child receives no model credential."""

    def __init__(self, *, executable: Path, script: Path, protocol_root: Path) -> None:
        self._command = _fixed_command(executable, script)
        self._bridge = HarnessPublicationBridge(protocol_root)
        self._environment = _allowlisted_environment(os.environ, model=False)

    def inspect(self, text: str, *, correlation_id: str) -> EgressDecision:
        request_id = str(uuid4())
        try:
            request = self._bridge.build_egress_request(request_id, correlation_id, text)
            result = _run_bounded_process(
                self._command,
                encode_one_json_line(request, EGRESS_STDIN_LIMIT),
                self._environment,
                5.0,
                EGRESS_STDOUT_LIMIT,
                None,
            )
            if result.timed_out or result.cancelled or result.overflowed or result.stderr_count > 0 or result.returncode != 0:
                return EgressDecision.unsafe((ModelFailureCode.FINAL_EGRESS_PROCESS_FAILED.value,))
            value = parse_one_json_line(result.stdout, EGRESS_STDOUT_LIMIT)
            receipt = self._bridge.parse_egress_receipt(value, expected_request_id=request_id)
        except Exception:
            return EgressDecision.unsafe((ModelFailureCode.FINAL_EGRESS_PROCESS_FAILED.value,))
        if receipt["status"] == "SAFE":
            return EgressDecision.safe()
        return EgressDecision.unsafe(tuple(receipt["violations"]))


def _fixed_command(executable: Path, script: Path) -> tuple[str, str]:
    resolved_executable = executable.resolve(strict=True)
    resolved_script = script.resolve(strict=True)
    if not resolved_executable.is_file() or not resolved_script.is_file():
        raise ValueError("fixed process command must reference existing files")
    return str(resolved_executable), str(resolved_script)


def _allowlisted_environment(source: Mapping[str, str], *, model: bool) -> dict[str, str]:
    names = {"PATH", "Path", "SystemRoot", "SYSTEMROOT"}
    if model:
        names.update({"DEEPSEEK_HARNESS_DEV_ROOT", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DSH_HOME"})
    return {name: source[name] for name in names if name in source}


def _run_bounded_process(
    command: tuple[str, str],
    stdin: bytes,
    environment: Mapping[str, str],
    timeout_seconds: float,
    stdout_limit: int,
    cancellation: CancellationHandle | None,
) -> _ProcessResult:
    process = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=dict(environment),
        shell=False,
    )
    stdout = bytearray()
    stderr_count = 0
    overflowed = False
    lock = threading.Lock()

    def drain_stdout() -> None:
        nonlocal overflowed
        assert process.stdout is not None
        while chunk := process.stdout.read(4096):
            with lock:
                if len(stdout) + len(chunk) > stdout_limit:
                    overflowed = True
                elif not overflowed:
                    stdout.extend(chunk)

    def drain_stderr() -> None:
        nonlocal stderr_count
        assert process.stderr is not None
        while chunk := process.stderr.read(4096):
            with lock:
                stderr_count = min(STDERR_LIMIT + 1, stderr_count + len(chunk))

    out_thread = threading.Thread(target=drain_stdout, daemon=True)
    err_thread = threading.Thread(target=drain_stderr, daemon=True)
    out_thread.start()
    err_thread.start()
    timed_out = False
    cancelled = False
    start = time.monotonic()
    try:
        assert process.stdin is not None
        process.stdin.write(stdin)
        process.stdin.close()
        while process.poll() is None:
            if cancellation is not None and cancellation.is_cancelled():
                cancelled = True
                break
            if time.monotonic() - start >= timeout_seconds:
                timed_out = True
                break
            time.sleep(0.01)
    finally:
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=REAP_GRACE_SECONDS)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=REAP_GRACE_SECONDS)
                except (subprocess.TimeoutExpired, OSError):
                    pass
        out_thread.join(timeout=REAP_GRACE_SECONDS)
        err_thread.join(timeout=REAP_GRACE_SECONDS)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
    if cancelled or timed_out:
        stdout.clear()
    return _ProcessResult(bytes(stdout), int(process.returncode or 0), stderr_count, timed_out, cancelled, overflowed)
