from __future__ import annotations

import logging
from typing import Iterable

from .config import AppConfig, ServiceConfig
from .models import EventType, HealthStatus, Incident, ServiceSnapshot, StatusChange
from .notifier import SlackNotifier
from .providers import build_provider
from .state import StateStore, utc_now_iso

logger = logging.getLogger(__name__)


class StatusMonitor:
    def __init__(self, config: AppConfig, store: StateStore, notifier: SlackNotifier) -> None:
        self.config = config
        self.store = store
        self.notifier = notifier
        self.latest_snapshots: dict[str, ServiceSnapshot] = {}
        self.latest_errors: dict[str, str] = {}

    def run_once(self, *, seed: bool = False) -> list[StatusChange]:
        all_changes: list[StatusChange] = []
        snapshots: list[ServiceSnapshot] = []
        errors: dict[str, str] = {}

        for service in self.config.services:
            if not service.enabled:
                logger.info("Skipping disabled service %s", service.name)
                continue
            try:
                snapshot = self._fetch_service(service)
                self.latest_snapshots[service.name] = snapshot
                self.latest_errors.pop(service.name, None)
                snapshots.append(snapshot)
                changes = self.diff_snapshot(snapshot)
                all_changes.extend(changes)
            except Exception as exc:
                logger.exception("Failed to poll service %s", service.name)
                errors[service.name] = str(exc)
                self.latest_errors[service.name] = str(exc)
                if service.name in self.latest_snapshots:
                    snapshots.append(self.latest_snapshots[service.name])
                else:
                    snapshots.append(
                        ServiceSnapshot(
                            service=service.name,
                            overall_status=HealthStatus.UNKNOWN,
                            incidents=[],
                            status_page_url=service.status_page_url,
                            fetched_at=utc_now_iso(),
                        )
                    )

        self.store.save_dashboard_status(snapshots, errors)

        if not all_changes:
            logger.info("No status changes detected")
            return all_changes

        self.store.append_audit(all_changes)
        if seed:
            logger.info(
                "Seed mode: recording %s change(s) without Slack notifications",
                len(all_changes),
            )
        else:
            self.notifier.notify_many(all_changes)
        self.store.save()
        return all_changes

    def _fetch_service(self, service: ServiceConfig) -> ServiceSnapshot:
        provider = build_provider(service.provider, self.config.http_timeout_seconds)
        logger.info("Polling %s via %s", service.name, service.provider)
        snapshot = provider.fetch(service)
        logger.info(
            "%s overall=%s open_incidents=%s",
            service.name,
            snapshot.overall_status.value,
            len(snapshot.incidents),
        )
        return snapshot

    def diff_snapshot(self, snapshot: ServiceSnapshot) -> list[StatusChange]:
        changes: list[StatusChange] = []
        detected_at = utc_now_iso()
        current_keys = {incident.key for incident in snapshot.incidents}
        previous = self.store.known_for_service(snapshot.service)

        for incident in snapshot.incidents:
            known = previous.get(incident.key)
            if known is None:
                changes.append(
                    StatusChange(
                        event_type=EventType.CREATED,
                        incident=incident,
                        previous=None,
                        detected_at=detected_at,
                    )
                )
                self.store.upsert(incident)
                continue

            if known.fingerprint != incident.fingerprint:
                changes.append(
                    StatusChange(
                        event_type=EventType.UPDATED,
                        incident=incident,
                        previous=known,
                        detected_at=detected_at,
                    )
                )
                self.store.upsert(incident)

        for key, known in previous.items():
            if key in current_keys:
                continue
            recovered = Incident(
                service=known.service,
                incident_id=known.incident_id,
                title=known.title,
                status=HealthStatus.OPERATIONAL,
                updated_at=detected_at,
                status_page_url=known.status_page_url,
                incident_url=known.incident_url or known.status_page_url,
                impact=known.impact,
                raw_status="resolved",
            )
            changes.append(
                StatusChange(
                    event_type=EventType.RECOVERED,
                    incident=recovered,
                    previous=known,
                    detected_at=detected_at,
                )
            )
            self.store.remove(key)

        return changes

    def dashboard_payload(self) -> dict:
        status = self.store.load_dashboard_status()
        open_incidents = [incident.to_dict() for incident in self.store.all_incidents()]
        return {
            "updated_at": status.get("updated_at"),
            "services": status.get("services", []),
            "open_incidents": open_incidents,
            "recent_events": self.store.read_audit(limit=40),
            "slack_enabled": bool(self.config.slack_webhook_url) and not self.config.dry_run,
            "dry_run": self.config.dry_run,
            "poll_interval_seconds": self.config.poll_interval_seconds,
        }


def summarize_changes(changes: Iterable[StatusChange]) -> str:
    items = list(changes)
    if not items:
        return "No changes"
    parts = [
        f"{change.event_type.value}:{change.incident.service}:{change.incident.incident_id}"
        for change in items
    ]
    return ", ".join(parts)
