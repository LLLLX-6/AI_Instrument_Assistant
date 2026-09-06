from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

from ai_instrument_assistant.application.services import (
    AnalysisFailedError,
    ArtifactUnavailableError,
    MeasurementService,
)
from ai_instrument_assistant.application.tool_contracts import (
    ToolContractValidationError,
    serialize_instrument_status,
    serialize_measurement_result,
)
from ai_instrument_assistant.domain.instrument import (
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDisconnectedError,
    InstrumentIdentityMismatchError,
    WaveformAcquisitionError,
)
from ai_instrument_assistant.domain.measurement import (
    MeasurementKind,
    MeasurementQuality,
    MeasurementRequest,
)


class _ContractValidator(Protocol):
    def validate_request(self, payload: Any) -> None: ...

    def validate_runtime_response(self, payload: Any) -> None: ...


class HardwareToolRuntime:
    """Execute exactly the reviewed hardware semantic-operation allowlist."""

    def __init__(
        self,
        service: MeasurementService,
        validator: _ContractValidator,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._service = service
        self._validator = validator
        self._id_factory = id_factory
        self._workflow_lock = Lock()
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "hardware.get_status": self._handle_status,
            "hardware.measure_frequency": self._handle_frequency,
            "hardware.measure_vpp": self._handle_vpp,
            "hardware.capture_waveform": self._handle_waveform,
            "hardware.measure_pwm": self._handle_pwm,
        }

    def execute(self, payload: Any) -> dict[str, Any]:
        operation = self._safe_operation(payload)
        if operation is not None and operation not in self._handlers:
            return self._error(operation, "unsupported_operation")
        try:
            self._validator.validate_request(payload)
        except ToolContractValidationError as error:
            return self._error(
                operation,
                "invalid_request",
                issues=tuple(
                    {"path": issue.path, "rule": issue.rule}
                    for issue in error.issues
                ),
            )

        assert operation is not None
        try:
            with self._workflow_lock:
                response = self._handlers[operation](payload["arguments"])
            self._validator.validate_runtime_response(response)
            return response
        except ToolContractValidationError:
            return self._error(operation, "internal_error")
        except InstrumentIdentityMismatchError:
            return self._error(operation, "instrument_identity_mismatch")
        except InstrumentDisconnectedError:
            return self._error(operation, "hardware_unavailable")
        except InstrumentConnectionError:
            return self._error(operation, "instrument_connection_failed")
        except WaveformAcquisitionError:
            return self._error(operation, "waveform_acquisition_failed")
        except AnalysisFailedError:
            return self._error(operation, "analysis_failed")
        except ArtifactUnavailableError:
            return self._error(operation, "artifact_unavailable")
        except InstrumentCommandError:
            return self._error(operation, "measurement_failed")
        except Exception:
            return self._error(operation, "internal_error")

    def _handle_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        del arguments
        return self._success(serialize_instrument_status(self._service.get_status()))

    def _handle_frequency(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._measurement(arguments, MeasurementKind.FREQUENCY)

    def _handle_vpp(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._measurement(arguments, MeasurementKind.VPP)

    def _handle_waveform(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._measurement(arguments, MeasurementKind.WAVEFORM)

    def _handle_pwm(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._measurement(arguments, MeasurementKind.PWM)

    def _measurement(
        self,
        arguments: dict[str, Any],
        kind: MeasurementKind,
    ) -> dict[str, Any]:
        request_id = self._id_factory()
        if not isinstance(request_id, UUID):
            raise TypeError("id_factory must return UUID")
        result = self._service.measure(MeasurementRequest(
            request_id=request_id,
            kind=kind,
            channel=arguments["channel"],
            context_id=arguments.get("context_id"),
        ))
        if result.quality is MeasurementQuality.FAILED:
            code = (
                "waveform_acquisition_failed"
                if "waveform_unavailable" in result.warnings
                else "measurement_failed"
            )
            return self._error(self._operation_for(kind), code)
        return self._success(serialize_measurement_result(result))

    @staticmethod
    def _success(serialized: dict[str, Any]) -> dict[str, Any]:
        return {
            "contract_version": serialized["contract_version"],
            "ok": True,
            "operation": serialized["operation"],
            "result": serialized["result"],
        }

    def _error(
        self,
        operation: str | None,
        code: str,
        *,
        issues: tuple[dict[str, str], ...] = (),
    ) -> dict[str, Any]:
        messages = {
            "invalid_request": "The hardware tool request is invalid.",
            "unsupported_operation": "The hardware operation is not supported.",
            "hardware_unavailable": "The hardware is not available.",
            "instrument_connection_failed": "The instrument connection failed.",
            "instrument_identity_mismatch": "The connected instrument is incompatible.",
            "measurement_failed": "The measurement could not be completed.",
            "waveform_acquisition_failed": "The waveform could not be acquired.",
            "analysis_failed": "The waveform analysis could not be completed.",
            "artifact_unavailable": "The measurement artifact is unavailable.",
            "internal_error": "The hardware tool encountered an internal error.",
        }
        response: dict[str, Any] = {
            "contract_version": "1.0",
            "ok": False,
            "operation": operation,
            "error": {
                "code": code,
                "message": messages[code],
                "details": {"issues": list(issues)} if issues else {},
            },
        }
        self._validator.validate_runtime_response(response)
        return response

    @staticmethod
    def _safe_operation(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        operation = payload.get("operation")
        if (
            not isinstance(operation, str)
            or not operation
            or len(operation) > 128
            or any(ord(character) < 32 for character in operation)
        ):
            return None
        return operation

    @staticmethod
    def _operation_for(kind: MeasurementKind) -> str:
        return {
            MeasurementKind.FREQUENCY: "hardware.measure_frequency",
            MeasurementKind.VPP: "hardware.measure_vpp",
            MeasurementKind.WAVEFORM: "hardware.capture_waveform",
            MeasurementKind.PWM: "hardware.measure_pwm",
        }[kind]
