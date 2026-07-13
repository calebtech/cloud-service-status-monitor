from __future__ import annotations

from ..config import ServiceConfig
from ..models import HealthStatus, Incident, ServiceSnapshot
from ..state import utc_now_iso
from .base import StatusProvider

STATUSPAGE_INDICATOR_MAP = {
    "none": HealthStatus.OPERATIONAL,
    "minor": HealthStatus.DEGRADED,
    "major": HealthStatus.PARTIAL_OUTAGE,
    "critical": HealthStatus.MAJOR_OUTAGE,
    "maintenance": HealthStatus.MAINTENANCE,
}

INCIDENT_STATUS_MAP = {
    "investigating": HealthStatus.MAJOR_OUTAGE,
    "identified": HealthStatus.PARTIAL_OUTAGE,
    "monitoring": HealthStatus.DEGRADED,
    "resolved": HealthStatus.OPERATIONAL,
    "postmortem": HealthStatus.OPERATIONAL,
    "scheduled": HealthStatus.MAINTENANCE,
    "in_progress": HealthStatus.MAINTENANCE,
    "verifying": HealthStatus.MAINTENANCE,
    "completed": HealthStatus.OPERATIONAL,
}

IMPACT_MAP = {
    "none": HealthStatus.OPERATIONAL,
    "maintenance": HealthStatus.MAINTENANCE,
    "minor": HealthStatus.DEGRADED,
    "major": HealthStatus.PARTIAL_OUTAGE,
    "critical": HealthStatus.MAJOR_OUTAGE,
}


class StatuspageProvider(StatusProvider):
    """Atlassian Statuspage provider (GitHub, Cloudflare, etc.)."""

    name = "statuspage"

    def fetch(self, service: ServiceConfig) -> ServiceSnapshot:
        base_url = service.options.get("base_url", service.status_page_url).rstrip("/")
        unresolved = self.get_json(f"{base_url}/api/v2/incidents/unresolved.json")
        status_payload = self.get_json(f"{base_url}/api/v2/status.json")

        indicator = (status_payload.get("status") or {}).get("indicator", "none")
        overall = STATUSPAGE_INDICATOR_MAP.get(indicator, HealthStatus.UNKNOWN)

        incidents: list[Incident] = []
        for item in unresolved.get("incidents", []):
            incident_status = (item.get("status") or "").lower()
            impact = (item.get("impact") or "").lower()
            mapped = INCIDENT_STATUS_MAP.get(incident_status)
            if mapped is None or mapped == HealthStatus.OPERATIONAL:
                mapped = IMPACT_MAP.get(impact, HealthStatus.PARTIAL_OUTAGE)
            if incident_status == "resolved":
                mapped = HealthStatus.OPERATIONAL

            shortlink = item.get("shortlink") or item.get("short_link")
            incidents.append(
                Incident(
                    service=service.name,
                    incident_id=str(item["id"]),
                    title=item.get("name") or "Untitled incident",
                    status=mapped,
                    updated_at=item.get("updated_at") or utc_now_iso(),
                    status_page_url=service.status_page_url,
                    incident_url=shortlink,
                    impact=item.get("impact"),
                    raw_status=item.get("status"),
                )
            )

        return ServiceSnapshot(
            service=service.name,
            overall_status=overall,
            incidents=incidents,
            status_page_url=service.status_page_url,
            fetched_at=utc_now_iso(),
        )
