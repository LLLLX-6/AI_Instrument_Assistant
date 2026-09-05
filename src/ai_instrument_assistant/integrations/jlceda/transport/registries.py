from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ConnectionRecord:
    connection_id: str
    remote_host: str


class ConnectionRegistry:
    def __init__(self) -> None:
        self._records: dict[str, ConnectionRecord] = {}

    def add(self, connection_id: str, remote_host: str) -> ConnectionRecord:
        try:
            is_loopback = ipaddress.ip_address(remote_host).is_loopback
        except ValueError as error:
            raise PermissionError("Remote endpoint is not a valid loopback address") from error
        if not is_loopback:
            raise PermissionError("AIA-JLCEDA accepts loopback connections only")
        record = ConnectionRecord(connection_id, remote_host)
        self._records[connection_id] = record
        return record

    def require(self, connection_id: str) -> ConnectionRecord:
        try:
            return self._records[connection_id]
        except KeyError as error:
            raise ConnectionError("Connection is not registered") from error

    def remove(self, connection_id: str) -> None:
        self._records.pop(connection_id, None)


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    connection_id: str
    last_seen_at: datetime


class SessionRegistry:
    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}

    def __len__(self) -> int:
        return len(self._records)

    def add(self, record: SessionRecord) -> None:
        self.remove_for_connection(record.connection_id)
        self._records[record.session_id] = record

    def require(self, session_id: str, connection_id: str) -> SessionRecord:
        record = self._records.get(session_id)
        if record is None or record.connection_id != connection_id:
            raise PermissionError("Session is absent, expired, or belongs to another connection")
        return record

    def is_active(self, session_id: str) -> bool:
        return session_id in self._records

    def remove_for_connection(self, connection_id: str) -> None:
        for session_id in tuple(self._records):
            if self._records[session_id].connection_id == connection_id:
                del self._records[session_id]

    def expired_connections(self, now: datetime, timeout_seconds: float) -> list[str]:
        return sorted(
            record.connection_id
            for record in self._records.values()
            if (now - record.last_seen_at).total_seconds() > timeout_seconds
        )
