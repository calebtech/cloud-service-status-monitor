from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import Incident, ServiceSnapshot, StatusChange

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class StateStore:
    """Persists known incidents for deduplication, dashboard status, and audit history."""

    def __init__(self, state_path: Path, audit_path: Path, status_path: Path | None = None) -> None:
        self.state_path = state_path
        self.audit_path = audit_path
        self.status_path = status_path or (state_path.parent / "latest_status.json")
        self._incidents: dict[str, Incident] = {}
        self._load()

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            for item in payload.get("incidents", []):
                incident = Incident.from_dict(item)
                self._incidents[incident.key] = incident
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Failed to load state from %s: %s", self.state_path, exc)

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": utc_now_iso(),
            "incidents": [incident.to_dict() for incident in self._incidents.values()],
        }
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.state_path)

    def get(self, key: str) -> Incident | None:
        return self._incidents.get(key)

    def upsert(self, incident: Incident) -> None:
        self._incidents[incident.key] = incident

    def remove(self, key: str) -> None:
        self._incidents.pop(key, None)

    def all_incidents(self) -> list[Incident]:
        return list(self._incidents.values())

    def known_for_service(self, service: str) -> dict[str, Incident]:
        return {
            key: incident
            for key, incident in self._incidents.items()
            if incident.service == service
        }

    def append_audit(self, changes: Iterable[StatusChange]) -> None:
        records = [change.to_audit_record() for change in changes]
        if not records:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    def save_dashboard_status(
        self,
        snapshots: list[ServiceSnapshot],
        errors: dict[str, str] | None = None,
    ) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": utc_now_iso(),
            "services": [
                {
                    "service": snap.service,
                    "overall_status": snap.overall_status.value,
                    "status_page_url": snap.status_page_url,
                    "fetched_at": snap.fetched_at,
                    "open_incident_count": len(snap.incidents),
                    "incidents": [incident.to_dict() for incident in snap.incidents],
                    "error": (errors or {}).get(snap.service),
                }
                for snap in snapshots
            ],
        }
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.status_path)

    def load_dashboard_status(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {"updated_at": None, "services": []}
        try:
            return json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load dashboard status: %s", exc)
            return {"updated_at": None, "services": []}

    def read_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        try:
            lines = self.audit_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            logger.warning("Failed to read audit log: %s", exc)
            return []
        records: list[dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(records) >= limit:
                break
        return records
