from __future__ import annotations

import json

import requests

from abc import ABC, abstractmethod

from ..config import ServiceConfig
from ..models import ServiceSnapshot


class StatusProvider(ABC):
    name: str

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "cloud-service-status-monitor/1.0",
                "Accept": "application/json",
            }
        )

    @abstractmethod
    def fetch(self, service: ServiceConfig) -> ServiceSnapshot:
        raise NotImplementedError

    def get_json(self, url: str) -> dict | list:
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "utf-16" in content_type or response.content.startswith(b"\xfe\xff"):
            return json.loads(response.content.decode("utf-16"))
        if response.content.startswith(b"\xff\xfe"):
            return json.loads(response.content.decode("utf-16"))
        return response.json()
