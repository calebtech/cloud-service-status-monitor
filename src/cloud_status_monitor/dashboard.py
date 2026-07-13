from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template_string

from .monitor import StatusMonitor, summarize_changes

logger = logging.getLogger(__name__)

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Cloud Service Status</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg: #070b16;
      --bg-mid: #121833;
      --surface: rgba(16, 22, 42, 0.72);
      --text: #f8fafc;
      --muted: #a5b0d0;
      --lavender: #9aa0ff;
      --orange: #ff7a45;
      --border: rgba(154, 160, 255, 0.18);
      --accent: #9aa0ff;
      --ok: #39d353;
      --warn: #ffb020;
      --bad: #ff5c7a;
      --maint: #9aa0ff;
      --unknown: #8b93b0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "DM Sans", sans-serif;
      color: var(--text);
      min-height: 100vh;
      background:
        radial-gradient(ellipse 80% 55% at 50% 28%, #1a2450 0%, transparent 58%),
        radial-gradient(ellipse 120% 80% at 50% 100%, #05070f 0%, var(--bg) 55%);
      background-color: var(--bg);
      position: relative;
      overflow-x: hidden;
    }
    body::before {
      content: "";
      position: fixed;
      inset: -20% 0 0;
      pointer-events: none;
      z-index: 0;
      background:
        radial-gradient(circle at 50% 34%, transparent 0 11%, rgba(154, 160, 255, 0.07) 11.2% 11.35%, transparent 11.5%),
        radial-gradient(circle at 50% 34%, transparent 0 18%, rgba(154, 160, 255, 0.06) 18.2% 18.35%, transparent 18.5%),
        radial-gradient(circle at 50% 34%, transparent 0 26%, rgba(154, 160, 255, 0.05) 26.2% 26.35%, transparent 26.5%),
        radial-gradient(circle at 50% 34%, transparent 0 35%, rgba(154, 160, 255, 0.04) 35.2% 35.35%, transparent 35.5%),
        radial-gradient(circle at 50% 34%, transparent 0 45%, rgba(154, 160, 255, 0.03) 45.2% 45.35%, transparent 45.5%);
    }
    body::after {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: 0;
      background:
        radial-gradient(circle at 18% 22%, #39d353 0 1.5px, transparent 2.5px),
        radial-gradient(circle at 78% 18%, #ff7a45 0 1.5px, transparent 2.5px),
        radial-gradient(circle at 86% 42%, #9aa0ff 0 1.5px, transparent 2.5px),
        radial-gradient(circle at 12% 58%, #ff7a45 0 1px, transparent 2px),
        radial-gradient(circle at 70% 72%, #39d353 0 1px, transparent 2px),
        radial-gradient(circle at 42% 14%, #9aa0ff 0 1px, transparent 2px),
        radial-gradient(circle at 92% 68%, #ff7a45 0 1.5px, transparent 2.5px),
        radial-gradient(circle at 28% 80%, #9aa0ff 0 1px, transparent 2px);
      opacity: 0.9;
    }
    .wrap {
      position: relative;
      z-index: 1;
      max-width: 1100px;
      margin: 0 auto;
      padding: 2rem 1.25rem 3rem;
    }
    .mission-bar {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: center;
      margin-bottom: 1.25rem;
      color: var(--lavender);
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .mission-bar .live {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
    }
    .mission-bar .live::before {
      content: "";
      width: 0.45rem;
      height: 0.45rem;
      border-radius: 50%;
      background: var(--ok);
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 0.55rem;
      color: var(--orange);
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-bottom: 0.55rem;
    }
    .eyebrow::before {
      content: "";
      width: 1.4rem;
      height: 1px;
      background: var(--orange);
    }
    header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 1rem;
      align-items: flex-end;
      margin-bottom: 1.75rem;
    }
    .brand {
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      line-height: 1.1;
      color: #fff;
    }
    .tagline {
      margin-top: 0.45rem;
      color: var(--lavender);
      font-size: 0.95rem;
    }
    .meta {
      text-align: right;
      color: var(--muted);
      font-size: 0.85rem;
      font-family: "JetBrains Mono", monospace;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }
    .stat {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1rem 1.1rem;
      backdrop-filter: blur(8px);
    }
    .stat .label {
      color: var(--lavender);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .stat .value {
      margin-top: 0.35rem;
      font-size: 1.6rem;
      font-weight: 700;
      font-family: "JetBrains Mono", monospace;
      color: #fff;
    }
    .services {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }
    .service {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.1rem 1.2rem;
      display: flex;
      flex-direction: column;
      gap: 0.7rem;
      backdrop-filter: blur(8px);
    }
    .service-top {
      display: flex;
      justify-content: space-between;
      gap: 0.75rem;
      align-items: flex-start;
    }
    .service-name {
      font-size: 1.15rem;
      font-weight: 600;
      color: #fff;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      border-radius: 999px;
      padding: 0.25rem 0.65rem;
      font-size: 0.78rem;
      font-weight: 600;
      border: 1px solid var(--border);
      white-space: nowrap;
      background: rgba(7, 11, 22, 0.55);
    }
    .dot {
      width: 0.55rem;
      height: 0.55rem;
      border-radius: 50%;
      background: currentColor;
    }
    .status-operational { color: var(--ok); border-color: rgba(57, 211, 83, 0.35); }
    .status-degraded { color: var(--warn); border-color: rgba(255, 176, 32, 0.35); }
    .status-partial { color: var(--orange); border-color: rgba(255, 122, 69, 0.35); }
    .status-major { color: var(--bad); border-color: rgba(255, 92, 122, 0.4); }
    .status-maintenance { color: var(--maint); border-color: rgba(154, 160, 255, 0.35); }
    .status-unknown { color: var(--unknown); border-color: rgba(139, 147, 176, 0.35); }
    .service-meta {
      color: var(--muted);
      font-size: 0.85rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
    }
    .service-meta a,
    td a {
      color: var(--lavender);
      text-decoration: none;
      font-weight: 500;
    }
    .service-meta a:hover,
    td a:hover { color: #fff; text-decoration: underline; }
    .error {
      color: var(--bad);
      font-size: 0.8rem;
      font-family: "JetBrains Mono", monospace;
    }
    section h2 {
      font-size: 1rem;
      font-weight: 600;
      margin: 0 0 0.75rem;
      color: #fff;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1rem 1.1rem;
      margin-bottom: 1rem;
      overflow-x: auto;
      backdrop-filter: blur(8px);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
    }
    th, td {
      text-align: left;
      padding: 0.65rem 0.4rem;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
      color: var(--text);
    }
    th {
      color: var(--lavender);
      font-weight: 500;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    td.mono, .mono {
      font-family: "JetBrains Mono", monospace;
      font-size: 0.8rem;
      color: var(--muted);
    }
    .empty {
      color: var(--muted);
      padding: 0.75rem 0;
    }
    footer {
      margin-top: 1.25rem;
      color: var(--muted);
      font-size: 0.8rem;
    }
    @media (max-width: 800px) {
      .summary, .services { grid-template-columns: 1fr; }
      .meta { text-align: left; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="mission-bar">
      <span class="live">Mission log</span>
      <span>External services · status</span>
    </div>
    <header>
      <div>
        <div class="eyebrow">Incoming transmission</div>
        <div class="brand">Cloud Service Status</div>
        <div class="tagline">Unified health for AWS, GitLab, GitHub, and Docker Hub · Slack alerts on change</div>
      </div>
      <div class="meta">
        <div>Last refresh: <span id="updated-at">—</span></div>
        <div>Poll every <span id="poll-interval">—</span>s · Slack <span id="slack-state">—</span></div>
      </div>
    </header>

    <div class="summary">
      <div class="stat">
        <div class="label">Services monitored</div>
        <div class="value" id="stat-services">0</div>
      </div>
      <div class="stat">
        <div class="label">Open incidents</div>
        <div class="value" id="stat-incidents">0</div>
      </div>
      <div class="stat">
        <div class="label">Unhealthy services</div>
        <div class="value" id="stat-unhealthy">0</div>
      </div>
    </div>

    <div class="services" id="services"></div>

    <section>
      <h2>Open incidents</h2>
      <div class="panel" id="incidents-panel"></div>
    </section>

    <section>
      <h2>Recent detections</h2>
      <div class="panel" id="events-panel"></div>
    </section>

    <footer>Auto-refreshes every 15s from <span class="mono">/api/status</span>. Source of truth for Slack alerts and this dashboard is the same poller.</footer>
  </div>

  <script>
    const STATUS_CLASS = {
      "Operational": "status-operational",
      "Degraded Performance": "status-degraded",
      "Partial Outage": "status-partial",
      "Major Outage": "status-major",
      "Maintenance": "status-maintenance",
      "Unknown": "status-unknown",
    };

    function badge(status) {
      const cls = STATUS_CLASS[status] || "status-unknown";
      return `<span class="badge ${cls}"><span class="dot"></span>${status}</span>`;
    }

    function isHealthy(status) {
      return status === "Operational" || status === "Unknown";
    }

    function render(data) {
      document.getElementById("updated-at").textContent = data.updated_at || "waiting for first poll";
      document.getElementById("poll-interval").textContent = data.poll_interval_seconds ?? "—";
      document.getElementById("slack-state").textContent = data.dry_run
        ? "dry-run"
        : (data.slack_enabled ? "enabled" : "not configured");

      const services = data.services || [];
      const open = data.open_incidents || [];
      const unhealthy = services.filter(s => !isHealthy(s.overall_status) || s.error).length;

      document.getElementById("stat-services").textContent = services.length;
      document.getElementById("stat-incidents").textContent = open.length;
      document.getElementById("stat-unhealthy").textContent = unhealthy;

      document.getElementById("services").innerHTML = services.map(s => `
        <article class="service">
          <div class="service-top">
            <div class="service-name">${s.service}</div>
            ${badge(s.overall_status || "Unknown")}
          </div>
          <div class="service-meta">
            <span>${s.open_incident_count || 0} open</span>
            <span class="mono">checked ${s.fetched_at || "—"}</span>
            <a href="${s.status_page_url}" target="_blank" rel="noopener">Vendor status</a>
          </div>
          ${s.error ? `<div class="error">Poll error: ${s.error}</div>` : ""}
        </article>
      `).join("") || `<div class="empty">Waiting for first poll…</div>`;

      const incidentsPanel = document.getElementById("incidents-panel");
      if (!open.length) {
        incidentsPanel.innerHTML = `<div class="empty">No open incidents.</div>`;
      } else {
        incidentsPanel.innerHTML = `
          <table>
            <thead>
              <tr>
                <th>Service</th>
                <th>Status</th>
                <th>Title</th>
                <th>Updated</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              ${open.map(i => `
                <tr>
                  <td>${i.service}</td>
                  <td>${badge(i.status)}</td>
                  <td>${i.title}</td>
                  <td class="mono">${i.updated_at}</td>
                  <td><a href="${i.incident_url || i.status_page_url}" target="_blank" rel="noopener">Open</a></td>
                </tr>
              `).join("")}
            </tbody>
          </table>`;
      }

      const events = data.recent_events || [];
      const eventsPanel = document.getElementById("events-panel");
      if (!events.length) {
        eventsPanel.innerHTML = `<div class="empty">No audited events yet.</div>`;
      } else {
        eventsPanel.innerHTML = `
          <table>
            <thead>
              <tr>
                <th>Detected</th>
                <th>Event</th>
                <th>Service</th>
                <th>Status</th>
                <th>Title</th>
              </tr>
            </thead>
            <tbody>
              ${events.map(e => `
                <tr>
                  <td class="mono">${e.detected_at || "—"}</td>
                  <td class="mono">${e.event_type}</td>
                  <td>${e.incident?.service || "—"}</td>
                  <td>${badge(e.incident?.status || "Unknown")}</td>
                  <td>${e.incident?.title || "—"}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>`;
      }
    }

    async function refresh() {
      const res = await fetch("/api/status");
      const data = await res.json();
      render(data);
    }

    refresh();
    setInterval(refresh, 15000);
  </script>
</body>
</html>
"""


def create_app(monitor: StatusMonitor) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template_string(DASHBOARD_HTML)

    @app.get("/api/status")
    def api_status():
        return jsonify(monitor.dashboard_payload())

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app


def start_poll_loop(monitor: StatusMonitor, interval_seconds: int, stop_event: threading.Event) -> None:
    seed_first = False
    while not stop_event.is_set():
        try:
            changes = monitor.run_once(seed=seed_first)
            logger.info("Cycle complete: %s", summarize_changes(changes))
        except Exception:
            logger.exception("Poll loop failed")
        seed_first = False
        stop_event.wait(interval_seconds)


def serve_dashboard(
    monitor: StatusMonitor,
    *,
    host: str = "0.0.0.0",
    port: int = 8080,
) -> None:
    stop_event = threading.Event()
    worker = threading.Thread(
        target=start_poll_loop,
        args=(monitor, monitor.config.poll_interval_seconds, stop_event),
        name="status-poller",
        daemon=True,
    )
    worker.start()
    app = create_app(monitor)
    logger.info("Dashboard listening on http://%s:%s", host, port)
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    finally:
        stop_event.set()
