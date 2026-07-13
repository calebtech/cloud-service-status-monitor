from __future__ import annotations

from datetime import datetime, timezone

from ..config import ServiceConfig
from ..models import HealthStatus, Incident, ServiceSnapshot
from ..state import utc_now_iso
from .base import StatusProvider

# AWS public health event status codes used by status.aws.amazon.com/data.json
AWS_STATUS_MAP = {
    "0": HealthStatus.OPERATIONAL,
    "1": HealthStatus.DEGRADED,
    "2": HealthStatus.PARTIAL_OUTAGE,
    "3": HealthStatus.MAJOR_OUTAGE,
    0: HealthStatus.OPERATIONAL,
    1: HealthStatus.DEGRADED,
    2: HealthStatus.PARTIAL_OUTAGE,
    3: HealthStatus.MAJOR_OUTAGE,
}


def _ts_to_iso(value: str | int | float | None) -> str:
    if value is None:
        return utc_now_iso()
    try:
        ts = int(float(value))
        # Milliseconds vs seconds.
        if ts > 10_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value)


class AwsHealthProvider(StatusProvider):
    """AWS Health Dashboard public events feed."""

    name = "aws_health"

    def fetch(self, service: ServiceConfig) -> ServiceSnapshot:
        events_url = service.options.get(
            "events_url",
            "https://health.aws.amazon.com/public/currentevents",
        )
        events = self.get_json(events_url)
        if not isinstance(events, list):
            events = []

        incidents: list[Incident] = []
        severity = HealthStatus.OPERATIONAL
        severity_rank = {
            HealthStatus.OPERATIONAL: 0,
            HealthStatus.MAINTENANCE: 1,
            HealthStatus.DEGRADED: 2,
            HealthStatus.PARTIAL_OUTAGE: 3,
            HealthStatus.MAJOR_OUTAGE: 4,
            HealthStatus.UNKNOWN: 0,
        }

        for event in events:
            status_code = event.get("status", "0")
            mapped = AWS_STATUS_MAP.get(status_code, HealthStatus.UNKNOWN)
            if mapped == HealthStatus.OPERATIONAL:
                continue

            if severity_rank.get(mapped, 0) > severity_rank.get(severity, 0):
                severity = mapped

            arn = event.get("arn") or event.get("service") or event.get("summary")
            region = event.get("region_name") or "Global"
            service_name = event.get("service_name") or event.get("service") or "AWS"
            summary = event.get("summary") or "AWS service event"
            title = f"{service_name} ({region}): {summary}"

            logs = event.get("event_log") or []
            latest = logs[-1] if logs else {}
            updated_at = _ts_to_iso(latest.get("timestamp") or event.get("date"))

            incidents.append(
                Incident(
                    service=service.name,
                    incident_id=str(arn),
                    title=title[:240],
                    status=mapped,
                    updated_at=updated_at,
                    status_page_url=service.status_page_url,
                    incident_url=service.status_page_url,
                    impact=str(status_code),
                    raw_status=str(status_code),
                )
            )

        return ServiceSnapshot(
            service=service.name,
            overall_status=severity if incidents else HealthStatus.OPERATIONAL,
            incidents=incidents,
            status_page_url=service.status_page_url,
            fetched_at=utc_now_iso(),
        )
