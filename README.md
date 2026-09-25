# Typing Speed Game  Monitored on AWS

A small Flask-based typing speed game, instrumented with Prometheus metrics
and visualized in Grafana, deployed across two AWS free-tier EC2 instances.

## Architecture

```
                 ┌────────────────────────┐
   Public users  │   Instance 1 (App)     │
  ──────────────▶│  ┌──────────────────┐  │
                  │  │ Flask app :5000  │  │
                  │  │  + /metrics      │  │
                  │  └────────┬─────────┘  │
                  │           │             │
                  │  ┌────────▼─────────┐  │
                  │  │ Postgres (docker)│  │
                  │  └──────────────────┘  │
                  │  node-exporter :9100   │
                  └───────────┬────────────┘
                              │ private IP scrape
                  ┌───────────▼────────────┐
   Public users   │  Instance 2 (Monitor)  │
  ──────────────▶ │  Grafana :3000         │
                  │  Prometheus :9090      │
                  │  node-exporter :9100   │
                  └────────────────────────┘
```

- Instance 1 runs the game (Flask + Gunicorn), a Postgres container for
  scores, and node-exporter for host metrics.
- Instance 2 runs Prometheus (scraping Instance 1 over its private IP)
  and Grafana (dashboards, public-facing)
  
## Local development

```bash
cd app
docker build -t typing-game .
docker compose -f ../docker-compose.app.yml up
```

Visit http://localhost:5000

## Deploying to AWS

1. Launch two EC2 instances (see `docs/` or project notes for security group
   rules). Note Instance 1's private IP.
2. On Instance 1:
   ```bash
   git clone <this repo>
   cd typing-game-monitoring
   docker compose -f docker-compose.app.yml up -d
   ```
3. On Instance 2, edit `monitoring/prometheus.yml` and replace
   `INSTANCE_1_PRIVATE_IP` with Instance 1's actual private IP, then:
   ```bash
   docker compose -f docker-compose.monitoring.yml up -d
   ```
4. Open Grafana at `http://<instance-2-public-ip>:3000` (default login
   `admin` / value of `GRAFANA_ADMIN_PASSWORD`), add Prometheus
   (`http://prometheus:9090`) as a data source, and build dashboards for:
   - Request rate & P95 latency
   - Game sessions started/completed, WPM distribution
   - Host CPU/memory (node-exporter)

## Environment variables

| Variable | Used by | Default |
|---|---|---|
| `DB_PASSWORD` | app, db | `typinggame` |
| `GRAFANA_ADMIN_PASSWORD` | grafana | `changeme` |

Set real values in a `.env` file on each instance  don't commit them.

## Metrics exposed at `/metrics`

- `http_requests_total{method,endpoint,status}`
- `http_request_duration_seconds{endpoint}` (histogram)
- `game_sessions_started_total`
- `game_sessions_completed_total`
- `game_wpm` (histogram)

## Alerts

Defined in `monitoring/alerts.yml`:
- **AppDown** — fires if Prometheus can't scrape the app for 1 minute
- **HighRequestLatency** — fires if P95 latency exceeds 1s for 5 minutes
