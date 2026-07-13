from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ServiceConfig:
    name: str
    provider: str
    status_page_url: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppConfig:
    poll_interval_seconds: int = 300
    state_dir: Path = Path("./data")
    slack_webhook_url: str | None = None
    dry_run: bool = False
    http_timeout_seconds: int = 20
    services: list[ServiceConfig] = field(default_factory=list)

    @property
    def state_path(self) -> Path:
        return self.state_dir / "incident_state.json"

    @property
    def audit_path(self) -> Path:
        return self.state_dir / "incident_audit.jsonl"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    services: list[ServiceConfig] = []
    for item in raw.get("services", []):
        known = {"name", "provider", "status_page_url", "enabled"}
        options = {k: v for k, v in item.items() if k not in known}
        services.append(
            ServiceConfig(
                name=item["name"],
                provider=item["provider"],
                status_page_url=item["status_page_url"],
                enabled=bool(item.get("enabled", True)),
                options=options,
            )
        )

    slack_url = (
        os.getenv("SLACK_WEBHOOK_URL")
        or raw.get("slack", {}).get("webhook_url")
        or None
    )
    state_dir = Path(
        os.getenv("STATE_DIR")
        or raw.get("state_dir")
        or "./data"
    )

    return AppConfig(
        poll_interval_seconds=int(
            os.getenv("POLL_INTERVAL_SECONDS")
            or raw.get("poll_interval_seconds", 300)
        ),
        state_dir=state_dir,
        slack_webhook_url=slack_url,
        dry_run=_env_bool("DRY_RUN", bool(raw.get("dry_run", False))),
        http_timeout_seconds=int(raw.get("http_timeout_seconds", 20)),
        services=services,
    )
