from __future__ import annotations

from .aws import AwsHealthProvider
from .base import StatusProvider
from .statusio import StatusioProvider
from .statuspage import StatuspageProvider

PROVIDERS: dict[str, type[StatusProvider]] = {
    StatuspageProvider.name: StatuspageProvider,
    StatusioProvider.name: StatusioProvider,
    AwsHealthProvider.name: AwsHealthProvider,
}


def build_provider(name: str, timeout_seconds: int = 20) -> StatusProvider:
    try:
        provider_cls = PROVIDERS[name]
    except KeyError as exc:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unknown provider '{name}'. Known providers: {known}") from exc
    return provider_cls(timeout_seconds=timeout_seconds)
