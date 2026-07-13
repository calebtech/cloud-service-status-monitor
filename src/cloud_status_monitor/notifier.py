from __future__ import annotations

import logging
from typing import Iterable

import requests

from .models import EventType, StatusChange

logger = logging.getLogger(__name__)

EVENT_COLORS = {
    EventType.CREATED: "#E01E5A",
    EventType.UPDATED: "#ECB22E",
    EventType.RECOVERED: "#2EB67D",
}

EVENT_EMOJI = {
    EventType.CREATED: ":rotating_light:",
    EventType.UPDATED: ":warning:",
    EventType.RECOVERED: ":white_check_mark:",
}


class SlackNotifier:
    def __init__(self, webhook_url: str | None, *, dry_run: bool = False) -> None:
        self.webhook_url = webhook_url
        self.dry_run = dry_run
        self.session = requests.Session()

    def notify_many(self, changes: Iterable[StatusChange]) -> int:
        sent = 0
        for change in changes:
            self.notify(change)
            sent += 1
        return sent

    def notify(self, change: StatusChange) -> None:
        payload = self.build_payload(change)
        if self.dry_run or not self.webhook_url:
            logger.info(
                "DRY-RUN Slack notification [%s] %s — %s",
                change.event_type.value,
                change.incident.service,
                change.incident.title,
            )
            logger.debug("Payload: %s", payload)
            return

        response = self.session.post(self.webhook_url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info(
            "Sent Slack notification [%s] %s — %s",
            change.event_type.value,
            change.incident.service,
            change.incident.title,
        )

    def build_payload(self, change: StatusChange) -> dict:
        incident = change.incident
        emoji = EVENT_EMOJI[change.event_type]
        color = EVENT_COLORS[change.event_type]
        headline = {
            EventType.CREATED: "New incident detected",
            EventType.UPDATED: "Incident updated",
            EventType.RECOVERED: "Service recovered",
        }[change.event_type]

        link = incident.incident_url or incident.status_page_url
        text = (
            f"{emoji} *{headline}*: *{incident.service}* — {incident.title}\n"
            f"*Status:* {incident.status.value}\n"
            f"*Timestamp:* {incident.updated_at}\n"
            f"<{link}|View status page>"
        )

        fields = [
            {"title": "Service", "value": incident.service, "short": True},
            {"title": "Status", "value": incident.status.value, "short": True},
            {"title": "Incident", "value": incident.title, "short": False},
            {"title": "Timestamp", "value": incident.updated_at, "short": True},
            {"title": "Event", "value": change.event_type.value, "short": True},
        ]
        if incident.impact:
            fields.append({"title": "Impact", "value": incident.impact, "short": True})

        return {
            "text": text,
            "attachments": [
                {
                    "color": color,
                    "title": f"{incident.service}: {incident.title}",
                    "title_link": link,
                    "fields": fields,
                    "footer": "Cloud Service Status Monitor",
                }
            ],
        }
