from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cloud_status_monitor.config import ServiceConfig
from cloud_status_monitor.models import EventType, HealthStatus, Incident, ServiceSnapshot
from cloud_status_monitor.monitor import StatusMonitor
from cloud_status_monitor.providers.aws import AwsHealthProvider
from cloud_status_monitor.providers.statusio import StatusioProvider
from cloud_status_monitor.providers.statuspage import StatuspageProvider
from cloud_status_monitor.state import StateStore

FIXTURES = Path(__file__).parent / "fixtures"


def _service(name: str, provider: str, **options) -> ServiceConfig:
    return ServiceConfig(
        name=name,
        provider=provider,
        status_page_url=options.pop("status_page_url", "https://example.com"),
        options=options,
    )


def test_statuspage_provider_parses_unresolved(monkeypatch):
    unresolved = json.loads((FIXTURES / "statuspage_github_unresolved.json").read_text())
    status = json.loads((FIXTURES / "statuspage_github_status.json").read_text())
    provider = StatuspageProvider()

    def fake_get_json(url: str):
        if url.endswith("unresolved.json"):
            return unresolved
        return status

    monkeypatch.setattr(provider, "get_json", fake_get_json)
    snapshot = provider.fetch(_service("GitHub", "statuspage", base_url="https://www.githubstatus.com"))
    assert snapshot.overall_status == HealthStatus.OPERATIONAL
    assert snapshot.incidents == []


def test_statuspage_provider_maps_incident(monkeypatch):
    unresolved = {
        "incidents": [
            {
                "id": "abc123",
                "name": "API degraded",
                "status": "investigating",
                "impact": "major",
                "updated_at": "2026-07-13T10:00:00Z",
                "shortlink": "https://www.githubstatus.com/incidents/abc123",
            }
        ]
    }
    status = {"status": {"indicator": "major", "description": "Partial System Outage"}}
    provider = StatuspageProvider()
    monkeypatch.setattr(
        provider,
        "get_json",
        lambda url: unresolved if "unresolved" in url else status,
    )
    snapshot = provider.fetch(_service("GitHub", "statuspage", base_url="https://www.githubstatus.com"))
    assert snapshot.overall_status == HealthStatus.PARTIAL_OUTAGE
    assert len(snapshot.incidents) == 1
    assert snapshot.incidents[0].status == HealthStatus.MAJOR_OUTAGE
    assert snapshot.incidents[0].title == "API degraded"


def test_statusio_provider_operational(monkeypatch):
    payload = json.loads((FIXTURES / "statusio_docker.json").read_text())
    provider = StatusioProvider()
    monkeypatch.setattr(provider, "get_json", lambda url: payload)
    snapshot = provider.fetch(
        _service(
            "Docker Hub",
            "statusio",
            page_id="533c6539221ae15e3f000031",
            status_page_url="https://status.docker.com",
        )
    )
    assert snapshot.overall_status == HealthStatus.OPERATIONAL
    assert snapshot.incidents == []


def test_statusio_synthesizes_incident_when_degraded(monkeypatch):
    payload = {
        "result": {
            "status_overall": {"status": "Degraded Performance", "status_code": 300, "updated": "2026-07-13T10:00:00Z"},
            "status": [{"name": "Registry", "status": "Degraded Performance", "status_code": 300}],
            "incidents": [],
            "maintenance": [],
        }
    }
    provider = StatusioProvider()
    monkeypatch.setattr(provider, "get_json", lambda url: payload)
    snapshot = provider.fetch(
        _service("Docker Hub", "statusio", page_id="x", status_page_url="https://status.docker.com")
    )
    assert snapshot.overall_status == HealthStatus.DEGRADED
    assert len(snapshot.incidents) == 1
    assert "Registry" in snapshot.incidents[0].title


def test_aws_provider_maps_events(monkeypatch):
    events = json.loads((FIXTURES / "aws_events.json").read_text())
    provider = AwsHealthProvider()
    monkeypatch.setattr(provider, "get_json", lambda url: events)
    snapshot = provider.fetch(
        _service(
            "AWS",
            "aws_health",
            status_page_url="https://health.aws.amazon.com/health/status",
        )
    )
    assert snapshot.overall_status == HealthStatus.MAJOR_OUTAGE
    assert len(snapshot.incidents) == 1
    assert "Multiple services" in snapshot.incidents[0].title


def test_dedup_and_recovery(tmp_path):
    store = StateStore(tmp_path / "state.json", tmp_path / "audit.jsonl")
    notifier = MagicMock()
    monitor = StatusMonitor(MagicMock(), store, notifier)

    incident = Incident(
        service="GitHub",
        incident_id="1",
        title="Outage",
        status=HealthStatus.MAJOR_OUTAGE,
        updated_at="2026-07-13T10:00:00Z",
        status_page_url="https://www.githubstatus.com",
        incident_url="https://www.githubstatus.com/incidents/1",
        raw_status="investigating",
    )
    snapshot = ServiceSnapshot(
        service="GitHub",
        overall_status=HealthStatus.MAJOR_OUTAGE,
        incidents=[incident],
        status_page_url="https://www.githubstatus.com",
    )

    created = monitor.diff_snapshot(snapshot)
    assert len(created) == 1
    assert created[0].event_type == EventType.CREATED

    # Same fingerprint => no duplicate
    assert monitor.diff_snapshot(snapshot) == []

    updated = Incident(
        service="GitHub",
        incident_id="1",
        title="Outage",
        status=HealthStatus.DEGRADED,
        updated_at="2026-07-13T10:05:00Z",
        status_page_url="https://www.githubstatus.com",
        incident_url="https://www.githubstatus.com/incidents/1",
        raw_status="monitoring",
    )
    updates = monitor.diff_snapshot(
        ServiceSnapshot(
            service="GitHub",
            overall_status=HealthStatus.DEGRADED,
            incidents=[updated],
            status_page_url="https://www.githubstatus.com",
        )
    )
    assert len(updates) == 1
    assert updates[0].event_type == EventType.UPDATED

    recovered = monitor.diff_snapshot(
        ServiceSnapshot(
            service="GitHub",
            overall_status=HealthStatus.OPERATIONAL,
            incidents=[],
            status_page_url="https://www.githubstatus.com",
        )
    )
    assert len(recovered) == 1
    assert recovered[0].event_type == EventType.RECOVERED
    assert store.get("GitHub:1") is None
