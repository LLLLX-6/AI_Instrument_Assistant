from __future__ import annotations

import math
from functools import wraps
from threading import RLock
from typing import Any, Callable, TypeVar

from ai_instrument_assistant.application.ports.oscilloscope import (
    ChannelCoupling,
    OscilloscopeInterface,
)
from ai_instrument_assistant.communication.errors import (
    TransportDisconnectedError,
    TransportError,
    TransportTimeoutError,
)
from ai_instrument_assistant.communication.scpi_session import ScpiSession
from ai_instrument_assistant.communication.visa import VisaTransport
from ai_instrument_assistant.domain.instrument.models import InstrumentIdentity
from ai_instrument_assistant.hardware.errors import (
    HardwareError,
    InstrumentCommandError,
    InstrumentConnectionError,
    InstrumentDisconnectedError,
    InstrumentIdentityMismatchError,
    InstrumentResponseError,
    InstrumentStateVerificationError,
    InstrumentTimeoutError,
)


_MODEL = "DS1102Z-E"
_MANUFACTURER = "RIGOL TECHNOLOGIES"
# Observed on firmware 00.06.03.SP2 when no measurable periodic signal existed.
# This is a bounded compatibility rule, not claimed as a manual-wide sentinel spec.
_OBSERVED_UNAVAILABLE_FREQUENCY = 9.9e37
_PROBE_RATIOS = (
    0.01, 0.02, 0.05, 0.1, 0.2, 0.5,
    1.0, 2.0, 5.0, 10.0, 20.0, 50.0,
    100.0, 200.0, 500.0, 1000.0,
)
_Result = TypeVar("_Result")


def _serialized(method: Callable[..., _Result]) -> Callable[..., _Result]:
    """Keep each semantic operation, including read-back, atomic in-process."""

    @wraps(method)
    def wrapper(self: DS1102ZEDriver, *args: Any, **kwargs: Any) -> _Result:
        with self._operation_lock:
            return method(self, *args, **kwargs)

    return wrapper


class DS1102ZEDriver(OscilloscopeInterface):
    """Minimal DS1102Z-E driver backed only by Phase 6A audited SCPI."""

    def __init__(
        self,
        transport: VisaTransport,
        resource_name: str,
        *,
        timeout_seconds: float,
    ) -> None:
        if not isinstance(resource_name, str) or not resource_name.strip():
            raise ValueError("resource_name must be a non-empty string")
        timeout = _finite_number(timeout_seconds, "timeout_seconds")
        if timeout <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._transport = transport
        self._resource_name = resource_name
        self._timeout_seconds = timeout
        self._session: ScpiSession | None = None
        self._identity: InstrumentIdentity | None = None
        self._operation_lock = RLock()

    @_serialized
    def connect(self) -> InstrumentIdentity:
        if self._session is not None and self._identity is not None:
            return self._identity
        try:
            connection = self._transport.open(
                self._resource_name, timeout_seconds=self._timeout_seconds
            )
        except TransportError as error:
            raise _connection_error(error, "Instrument connection failed") from error

        session = ScpiSession(connection)
        self._session = session
        try:
            identity = self._read_identity()
        except Exception:
            self._session = None
            self._identity = None
            try:
                session.close()
            except TransportError:
                pass
            raise
        self._identity = identity
        return identity

    @_serialized
    def disconnect(self) -> None:
        session = self._session
        self._session = None
        self._identity = None
        if session is None:
            return
        try:
            session.close()
        except TransportError as error:
            raise _connection_error(error, "Instrument disconnect failed") from error

    @_serialized
    def get_identity(self) -> InstrumentIdentity:
        self._require_session()
        if self._identity is None:
            raise InstrumentDisconnectedError("Instrument identity is unavailable")
        return self._identity

    @_serialized
    def get_channel_enabled(self, channel: int) -> bool:
        _require_channel(channel)
        response = self._query(f":CHANnel{channel}:DISPlay?", "channel display")
        if response == "1":
            return True
        if response == "0":
            return False
        raise InstrumentResponseError("Channel display response is invalid")

    @_serialized
    def set_channel_enabled(self, channel: int, enabled: bool) -> None:
        _require_channel(channel)
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be bool")
        self._require_session()
        self._write(
            f":CHANnel{channel}:DISPlay {'ON' if enabled else 'OFF'}",
            "channel display",
        )
        if self.get_channel_enabled(channel) is not enabled:
            raise InstrumentStateVerificationError(
                "Channel display post-condition failed"
            )

    @_serialized
    def get_channel_coupling(self, channel: int) -> ChannelCoupling:
        _require_channel(channel)
        response = self._query(f":CHANnel{channel}:COUPling?", "channel coupling")
        try:
            return ChannelCoupling(response)
        except ValueError as error:
            raise InstrumentResponseError("Channel coupling response is invalid") from error

    @_serialized
    def set_channel_coupling(self, channel: int, coupling: ChannelCoupling) -> None:
        _require_channel(channel)
        if not isinstance(coupling, ChannelCoupling):
            raise TypeError("coupling must be ChannelCoupling")
        self._require_session()
        self._write(f":CHANnel{channel}:COUPling {coupling.value}", "channel coupling")
        if self.get_channel_coupling(channel) is not coupling:
            raise InstrumentStateVerificationError(
                "Channel coupling post-condition failed"
            )

    @_serialized
    def get_channel_scale(self, channel: int) -> float:
        _require_channel(channel)
        if self._query(f":CHANnel{channel}:UNITs?", "channel units") != "VOLT":
            raise InstrumentStateVerificationError(
                "Channel scale is not expressed in volts"
            )
        value = _parse_float(
            self._query(f":CHANnel{channel}:SCALe?", "channel scale"),
            "channel scale",
        )
        if value <= 0:
            raise InstrumentResponseError("Channel scale response must be positive")
        return value

    @_serialized
    def set_channel_scale(self, channel: int, volts_per_div: float) -> None:
        _require_channel(channel)
        scale = _finite_number(volts_per_div, "volts_per_div")
        if scale <= 0:
            raise ValueError("volts_per_div must be positive")
        self._require_session()
        if self._query(f":CHANnel{channel}:UNITs?", "channel units") != "VOLT":
            raise InstrumentStateVerificationError(
                "Channel scale cannot be set as volts/div for non-voltage units"
            )
        vernier = self._query(f":CHANnel{channel}:VERNier?", "channel vernier")
        if vernier not in ("0", "1"):
            raise InstrumentResponseError("Channel vernier response is invalid")
        probe = self.get_probe_ratio(channel)
        if vernier == "0" and probe in (1.0, 10.0):
            _require_audited_channel_scale(probe, scale)
        self._write(f":CHANnel{channel}:SCALe {_scpi_number(scale)}", "channel scale")
        observed = _parse_float(
            self._query(f":CHANnel{channel}:SCALe?", "channel scale"),
            "channel scale",
        )
        if not _close(observed, scale):
            raise InstrumentStateVerificationError(
                "Channel scale post-condition failed"
            )

    @_serialized
    def get_probe_ratio(self, channel: int) -> float:
        _require_channel(channel)
        value = _parse_float(
            self._query(f":CHANnel{channel}:PROBe?", "probe ratio"),
            "probe ratio",
        )
        for allowed in _PROBE_RATIOS:
            if _close(value, allowed):
                return allowed
        raise InstrumentResponseError("Probe ratio response is outside the audited enum")

    @_serialized
    def set_probe_ratio(self, channel: int, ratio: float) -> None:
        _require_channel(channel)
        probe = _require_probe_ratio(ratio)
        self._require_session()
        self._write(f":CHANnel{channel}:PROBe {_scpi_number(probe)}", "probe ratio")
        if not _close(self.get_probe_ratio(channel), probe):
            raise InstrumentStateVerificationError("Probe ratio post-condition failed")

    @_serialized
    def get_timebase_scale(self) -> float:
        if self._query(":TIMebase:MODE?", "timebase mode") != "MAIN":
            raise InstrumentStateVerificationError("Main timebase mode is required")
        value = _parse_float(
            self._query(":TIMebase:MAIN:SCALe?", "timebase scale"),
            "timebase scale",
        )
        if value <= 0:
            raise InstrumentResponseError("Timebase scale response must be positive")
        return value

    @_serialized
    def set_timebase_scale(self, seconds_per_div: float) -> None:
        scale = _require_main_timebase_scale(seconds_per_div)
        self._require_session()
        if self._query(":TIMebase:MODE?", "timebase mode") != "MAIN":
            raise InstrumentStateVerificationError("Main timebase mode is required")
        self._write(f":TIMebase:MAIN:SCALe {_scpi_number(scale)}", "timebase scale")
        observed = _parse_float(
            self._query(":TIMebase:MAIN:SCALe?", "timebase scale"),
            "timebase scale",
        )
        if not _close(observed, scale):
            raise InstrumentStateVerificationError(
                "Timebase scale post-condition failed"
            )

    @_serialized
    def measure_frequency(self, channel: int) -> float:
        _require_channel(channel)
        value = _parse_float(
            self._query(
                f":MEASure:ITEM? FREQuency,CHANnel{channel}",
                "frequency measurement",
            ),
            "frequency measurement",
        )
        if value <= 0 or math.isclose(
            value,
            _OBSERVED_UNAVAILABLE_FREQUENCY,
            rel_tol=1e-12,
        ):
            raise InstrumentResponseError("Frequency measurement is unavailable")
        return value

    @_serialized
    def measure_vpp(self, channel: int) -> float:
        _require_channel(channel)
        value = _parse_float(
            self._query(
                f":MEASure:ITEM? VPP,CHANnel{channel}",
                "Vpp measurement",
            ),
            "Vpp measurement",
        )
        if value < 0:
            raise InstrumentResponseError("Vpp measurement is unavailable")
        return value

    def _read_identity(self) -> InstrumentIdentity:
        raw = self._query("*IDN?", "instrument identity")
        fields = tuple(field.strip() for field in raw.split(","))
        if len(fields) != 4:
            raise InstrumentResponseError(
                "Instrument identity response has an unexpected shape"
            )
        try:
            identity = InstrumentIdentity(
                manufacturer=fields[0],
                model=fields[1],
                serial_number=fields[2],
                firmware_version=fields[3],
                raw_identity=raw,
            )
        except ValueError as error:
            raise InstrumentResponseError(
                "Instrument identity contains invalid fields"
            ) from error
        if (
            identity.manufacturer.upper() != _MANUFACTURER
            or identity.model.upper() != _MODEL
        ):
            raise InstrumentIdentityMismatchError(
                "Connected instrument is not a supported RIGOL DS1102Z-E"
            )
        return identity

    def _require_session(self) -> ScpiSession:
        if self._session is None:
            raise InstrumentDisconnectedError("Instrument is not connected")
        return self._session

    def _write(self, command: str, operation: str) -> None:
        session = self._require_session()
        try:
            session.write(command)
        except TransportError as error:
            raise _operation_error(error, f"{operation} failed") from error

    def _query(self, command: str, operation: str) -> str:
        session = self._require_session()
        try:
            return session.query(command)
        except TransportError as error:
            raise _operation_error(error, f"{operation} failed") from error


def _connection_error(error: TransportError, message: str) -> HardwareError:
    if isinstance(error, TransportTimeoutError):
        return InstrumentTimeoutError(message)
    if isinstance(error, TransportDisconnectedError):
        return InstrumentDisconnectedError(message)
    return InstrumentConnectionError(message)


def _operation_error(error: TransportError, message: str) -> HardwareError:
    if isinstance(error, TransportTimeoutError):
        return InstrumentTimeoutError(message)
    if isinstance(error, TransportDisconnectedError):
        return InstrumentDisconnectedError(message)
    return InstrumentCommandError(message)


def _require_channel(channel: int) -> None:
    if isinstance(channel, bool) or channel not in (1, 2):
        raise ValueError("DS1102Z-E channel must be 1 or 2")


def _finite_number(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _require_probe_ratio(value: float) -> float:
    ratio = _finite_number(value, "ratio")
    if ratio not in _PROBE_RATIOS:
        raise ValueError("ratio must be one of the audited DS1102Z-E probe values")
    return ratio


def _require_audited_channel_scale(probe: float, scale: float) -> None:
    lower, upper = (0.001, 10.0) if probe == 1.0 else (0.01, 100.0)
    if not lower <= scale <= upper or not _is_125_step(scale):
        raise ValueError(
            "volts_per_div is outside the audited 1X/10X non-vernier range"
        )


def _require_main_timebase_scale(value: float) -> float:
    scale = _finite_number(value, "seconds_per_div")
    if not 2e-9 <= scale <= 50.0 or not _is_125_step(scale):
        raise ValueError("seconds_per_div is outside the audited MAIN 1-2-5 range")
    return scale


def _is_125_step(value: float) -> bool:
    exponent = math.floor(math.log10(value))
    mantissa = value / (10 ** exponent)
    return any(
        math.isclose(mantissa, allowed, rel_tol=1e-9, abs_tol=1e-12)
        for allowed in (1.0, 2.0, 5.0)
    )


def _parse_float(response: str, field: str) -> float:
    try:
        value = float(response)
    except ValueError as error:
        raise InstrumentResponseError(f"{field} response is not numeric") from error
    if not math.isfinite(value):
        raise InstrumentResponseError(f"{field} response is not finite")
    return value


def _scpi_number(value: float) -> str:
    return format(value, ".12g")


def _close(observed: float, expected: float) -> bool:
    return math.isclose(observed, expected, rel_tol=1e-9, abs_tol=1e-15)
