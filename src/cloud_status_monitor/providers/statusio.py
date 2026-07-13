from __future__ import annotations

from ..config import ServiceConfig
from ..models import HealthStatus, Incident, ServiceSnapshot
from ..state import utc_now_iso
from .base import StatusProvider

STATUSIO_CODE_MAP = {
    100: HealthStatus.OPERATIONAL,
    200: HealthStatus.MAINTENANCE,
    300: HealthStatus.DEGRADED,
    400: HealthStatus.PARTIAL_OUTAGE,
    500: HealthStatus.MAJOR_OUTAGE,
    600: HealthStatus.MAJOR_OUTAGE,
}

STATUSIO_TEXT_MAP = {
    "operational": HealthStatus.OPERATIONAL,
    "planned maintenance": HealthStatus.MAINTENANCE,
    "maintenance": HealthStatus.MAINTENANCE,
    "degraded performance": HealthStatus.DEGRADED,
    "partial service disruption": HealthStatus.PARTIAL_OUTAGE,
    "partial outage": HealthStatus.PARTIAL_OUTAGE,
    "service disruption": HealthStatus.MAJOR_OUTAGE,
    "major outage": HealthStatus.MAJOR_OUTAGE,
    "security issue": HealthStatus.MAJOR_OUTAGE,
}


def map_statusio_status(status: str | None, status_code: int | None) -> HealthStatus:
    if status_code is not None:
        mapped = STATUSIO_CODE_MAP.get(int(status_code))
        if mapped:
            return mapped
    if status:
        mapped = STATUSIO_TEXT_MAP.get(status.strip().lower())
        if mapped:
            return mapped
    return HealthStatus.UNKNOWN


class StatusioProvider(StatusProvider):
    """Status.io provider (GitLab, Docker Hub, etc.)."""

    name = "statusio"

    def fetch(self, service: ServiceConfig) -> ServiceSnapshot:
        page_id = service.options["page_id"]
        api_base = service.options.get("api_base", "https://api.status.io").rstrip("/")
        payload = self.get_json(f"{api_base}/1.0/status/{page_id}")
        result = payload.get("result") or payload

        overall_block = result.get("status_overall") or {}
        overall = map_statusio_status(
            overall_block.get("status"),
            overall_block.get("status_code"),
        )

        incidents: list[Incident] = []
        for item in result.get("incidents") or []:
            incident_id = str(
                item.get("id")
                or item.get("_id")
                or item.get("incident_id")
                or item.get("name")
            )
            messages = item.get("messages") or []
            latest = messages[0] if messages else {}
            status_code = latest.get("status") or item.get("status_code")
            status_text = latest.get("status_text") or item.get("status")
            if isinstance(status_text, int):
                status_code = status_text
                status_text = None

            mapped = map_statusio_status(status_text if isinstance(status_text, str) else None, status_code)
            updated_at = (
                latest.get("datetime")
                or item.get("datetime_open")
                or overall_block.get("updated")
                or utc_now_iso()
            )
            title = item.get("name") or latest.get("details") or "Untitled incident"
            incident_url = item.get("url") or f"{service.status_page_url.rstrip('/')}/pages/incident/{incident_id}"

            incidents.append(
                Incident(
                    service=service.name,
                    incident_id=incident_id,
                    title=str(title)[:240],
                    status=mapped if mapped != HealthStatus.OPERATIONAL else HealthStatus.PARTIAL_OUTAGE,
                    updated_at=str(updated_at),
                    status_page_url=service.status_page_url,
                    incident_url=incident_url,
                    impact=None,
                    raw_status=str(status_text or status_code or mapped.value),
                )
            )

        # Active maintenance windows that are not represented as incidents.
        for item in result.get("maintenance") or result.get("maintenance_active") or []:
            if isinstance(item, dict) and item.get("active") is False:
                continue
            if not isinstance(item, dict):
                continue
            incident_id = str(item.get("id") or item.get("_id") or item.get("name") or "maintenance")
            title = item.get("name") or "Scheduled maintenance"
            updated_at = item.get("datetime_open") or item.get("updated") or utc_now_iso()
            incidents.append(
                Incident(
                    service=service.name,
                    incident_id=f"maint-{incident_id}",
                    title=str(title)[:240],
                    status=HealthStatus.MAINTENANCE,
                    updated_at=str(updated_at),
                    status_page_url=service.status_page_url,
                    incident_url=service.status_page_url,
                    raw_status="maintenance",
                )
            )

        # If overall is unhealthy but no incident objects exist, synthesize one.
        if overall not in {HealthStatus.OPERATIONAL, HealthStatus.UNKNOWN} and not incidents:
            degraded_components = [
                component.get("name")
                for component in result.get("status") or []
                if map_statusio_status(component.get("status"), component.get("status_code"))
                not in {HealthStatus.OPERATIONAL, HealthStatus.UNKNOWN}
            ]
            detail = ", ".join(degraded_components[:5]) or overall.value
            incidents.append(
                Incident(
                    service=service.name,
                    incident_id=f"overall-{overall.value.lower().replace(' ', '-')}",
                    title=f"{service.name} status: {detail}",
                    status=overall,
                    updated_at=str(overall_block.get("updated") or utc_now_iso()),
                    status_page_url=service.status_page_url,
                    incident_url=service.status_page_url,
                    raw_status=str(overall_block.get("status") or overall.value),
                )
            )

        return ServiceSnapshot(
            service=service.name,
            overall_status=overall,
            incidents=incidents,
            status_page_url=service.status_page_url,
            fetched_at=utc_now_iso(),
        )
