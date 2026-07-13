from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .config import load_config
from .dashboard import serve_dashboard
from .monitor import StatusMonitor, summarize_changes
from .notifier import SlackNotifier
from .state import StateStore


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor external cloud service status pages, expose a dashboard, and alert Slack.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=str(Path("config/config.yaml")),
        help="Path to YAML configuration file",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously using poll_interval_seconds from config",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Serve the unified status dashboard and poll in the background",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Dashboard bind host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Dashboard bind port (default: 8080)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log Slack payloads without sending them",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Record current open incidents without sending Slack notifications",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    config = load_config(args.config)
    if args.dry_run:
        config.dry_run = True

    if not config.services:
        logging.error("No services configured in %s", args.config)
        return 2

    store = StateStore(config.state_path, config.audit_path)
    notifier = SlackNotifier(config.slack_webhook_url, dry_run=config.dry_run)
    monitor = StatusMonitor(config, store, notifier)

    logging.info(
        "Starting cloud status monitor (services=%s dry_run=%s seed=%s serve=%s)",
        [service.name for service in config.services if service.enabled],
        config.dry_run,
        args.seed,
        args.serve,
    )

    if args.serve:
        if args.seed:
            changes = monitor.run_once(seed=True)
            logging.info("Seed complete: %s", summarize_changes(changes))
        serve_dashboard(monitor, host=args.host, port=args.port)
        return 0

    while True:
        changes = monitor.run_once(seed=args.seed)
        logging.info("Cycle complete: %s", summarize_changes(changes))
        if not args.loop:
            break
        args.seed = False
        time.sleep(config.poll_interval_seconds)

    return 0


if __name__ == "__main__":
    sys.exit(main())
