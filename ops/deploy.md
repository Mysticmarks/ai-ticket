# Deployment playbook

This playbook describes how to deploy the AI Ticket service with TLS termination, bearer authentication, request throttling, and Prometheus metrics enabled via Docker Compose.

## 1. Prepare environment variables

Create a `.env` file or export variables in your shell to control runtime behaviour. The most commonly adjusted values are:

| Variable | Purpose |
|----------|---------|
| `KOBOLDCPP_API_URL` | KoboldCPP-compatible inference endpoint consumed by the dispatcher. |
| `LOG_LEVEL` | Structured logging level (`INFO`, `DEBUG`, etc.). |
| `RATE_LIMIT_REQUESTS` | Requests allowed per client within each `RATE_LIMIT_WINDOW_SECONDS`. |
| `RATE_LIMIT_WINDOW_SECONDS` | Duration of the rate limit window in seconds. |
| `METRICS_NAMESPACE` | Namespace prefix for Prometheus metrics. |
| `TLS_PORT` | Public port exposed by the TLS offload proxy (defaults to `8443`). |

> ℹ️ The Flask server automatically trusts proxy headers when `TRUST_PROXY_COUNT` is set (Compose defaults this to `1`).

## 2. Manage authentication secrets

1. Copy the helper file and replace the placeholder token:
   ```bash
   cp ops/secrets/ai_ticket_auth_token.txt.example ops/secrets/ai_ticket_auth_token.txt
   echo "super-secure-token" > ops/secrets/ai_ticket_auth_token.txt
   ```
2. Every line represents a valid bearer token. Requests must include either `Authorization: Bearer <token>` or `X-API-Key: <token>`.
3. The Docker Compose file mounts this file as a Docker secret and the application reads it via `AI_TICKET_AUTH_TOKEN_FILE`.

Rotate tokens by editing the file and restarting the `ai_ticket` service.

## 3. Provision TLS certificates

Place your TLS assets inside `ops/certs/` with the exact filenames `server.crt` and `server.key`. The bundled Nginx proxy terminates TLS using these files and forwards traffic to the Flask container over the internal network.

For local development you can generate self-signed certificates:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:4096 \
  -keyout ops/certs/server.key \
  -out ops/certs/server.crt \
  -subj "/CN=localhost"
```

## 4. Launch the stack

```bash
docker compose up --build
```

Key endpoints:

- Application JSON API: `https://localhost:${TLS_PORT:-8443}/event`
- Health probe: `https://localhost:${TLS_PORT:-8443}/health`
- Prometheus metrics: `https://localhost:${TLS_PORT:-8443}/metrics`

Logs emitted by both containers are structured JSON and can be shipped to your aggregation pipeline. The `ai_ticket` service includes graceful shutdown hooks that acknowledge termination signals before the container stops.

## 5. Operational tips

- **Request throttling** – tune `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_SECONDS` to suit your workload profile.
- **Proxy forwarding** – adjust `TRUST_PROXY_COUNT` when adding additional load balancers so the application uses the correct client IP for rate limiting.
- **Metrics scraping** – point Prometheus (or another scraper) at the `/metrics` endpoint exposed via the TLS proxy. The metrics follow the namespace configured by `METRICS_NAMESPACE`.
- **Secret rotation** – leverage Docker's `docker secret update` command (or re-create the file) to rotate tokens without rebuilding images.

## 6. Shutdown

Stop the stack gracefully with:

```bash
docker compose down
```

The application logs a shutdown event and flushes in-flight metrics counters before the process exits.
