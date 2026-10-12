# 📡 Store Status Monitor API

Automated monitoring service built with FastAPI and Playwright.

## Endpoints
* `GET /health`: Healthcheck status endpoint.
* `GET /check` / `POST /check`: Triggers a status check and sends alerts if state changes.

## Configuration
Configured via environment variables (see `.env.example`).
