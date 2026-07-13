from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class HealthStatus(str, Enum):
    OPERATIONAL = "Operational"
    DEGRADED = "Degraded Performance"
    PARTIAL_OUTAGE = "Partial Outage"
    MAJOR_OUTAGE = "Major Outage"
    MAINTENANCE = "Maintenance"
    UNKNOWN = "Unknown"

    @property
    def is_healthy(self) -> bool:
        return self in {HealthStatus.OPERATIONAL, HealthStatus.UNKNOWN}


class EventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class Incident:
    """Normalized incident across all status providers."""

    service: str
    incident_id: str
    title: str
    status: HealthStatus
    updated_at: str
    status_page_url: str
    incident_url: str | None = None
    impact: str | None = None
    raw_status: str | None = None

    @property
    def key(self) -> str:
        return f"{self.service}:{self.incident_id}"

    @property
    def fingerprint(self) -> str:
        return "|".join(
            [
                self.status.value,
                self.title.strip(),
                self.updated_at,
                self.raw_status or "",
                self.impact or "",
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Incident:
        return cls(
            service=data["service"],
            incident_id=data["incident_id"],
            title=data["title"],
            status=HealthStatus(data["status"]),
            updated_at=data["updated_at"],
            status_page_url=data["status_page_url"],
            incident_url=data.get("incident_url"),
            impact=data.get("impact"),
            raw_status=data.get("raw_status"),
        )


@dataclass
class StatusChange:
    event_type: EventType
    incident: Incident
    previous: Incident | None = None
    detected_at: str = ""

    def to_audit_record(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "detected_at": self.detected_at,
            "incident": self.incident.to_dict(),
            "previous": self.previous.to_dict() if self.previous else None,
        }


@dataclass
class ServiceSnapshot:
    service: str
    overall_status: HealthStatus
    incidents: list[Incident] = field(default_factory=list)
    status_page_url: str = ""
    fetched_at: str = ""
