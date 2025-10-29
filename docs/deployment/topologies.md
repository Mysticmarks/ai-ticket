# Deployment topologies

AI Ticket ships with a container-first workflow. This guide outlines the two supported deployment patterns and the
operational considerations around persistence, rate limiting, and TLS/offload.

## Single-node (Docker Compose)

The repository bundles `docker-compose.yml`, which starts two containers:

1. `ai_ticket` – the Flask/Gunicorn application serving `/event`, `/metrics`, and `/dashboard`.
2. `tls_proxy` – an nginx reverse proxy that terminates TLS and forwards requests to the application container.

Recommended steps:

- **Secrets & tokens** – copy `ops/secrets/ai_ticket_auth_token.txt.example` to
  `ops/secrets/ai_ticket_auth_token.txt` and populate with newline-delimited tokens. Compose mounts the file as a Docker
  secret and the server reloads it at runtime.
- **TLS materials** – place `server.crt`/`server.key` in `ops/certs/`. The proxy publishes
  `https://localhost:${TLS_PORT:-8443}` with automatic health checks against `/health`.
- **Rate limiting** – the default `RATE_LIMIT_BACKEND=memory` stores quotas inside the container. For a single-node
  deployment this is sufficient. To make quotas durable across restarts, set `RATE_LIMIT_BACKEND=sqlite` and mount a
  persistent volume to `RATE_LIMIT_SQLITE_PATH` (for example `./data/rate-limit.sqlite3`). The SQLite implementation
  coordinates access across multiple worker processes.
- **Metrics persistence** – configure `AI_TICKET_METRICS_DB=./data/metrics.sqlite3` (mounted via volume) to survive restarts
  and keep dashboard sparklines populated. Without the variable, metrics reset on each container reboot.
- **Backups** – periodically archive the mounted `data/` directory if you enable SQLite-backed rate limiting or metrics.

### Expected traffic flow

```
Client ──TLS──▶ tls_proxy (nginx) ──HTTP──▶ ai_ticket (Gunicorn)
```

Gunicorn listens on port `5000` inside the container. The proxy handles TLS termination, request logging, and path-based
routing to `/event`, `/metrics`, and `/dashboard`.

## Replicated application nodes (Kubernetes, Swarm, or manual scaling)

When running multiple application replicas, plan for shared state and TLS termination:

- **Ingress / TLS** – terminate TLS at your ingress controller or external proxy (e.g., nginx ingress, AWS ALB). Each
  application pod should listen on HTTP (`PORT`, default 5000). Set `TRUST_PROXY_COUNT` to the number of trusted hops so
  rate limiting and logging observe the real client IP.
- **Authentication tokens** – distribute the same token set to every replica (via Kubernetes Secret, HashiCorp Vault, etc.).
  The `TokenManager` reloads secrets on a timer when the file contents change.
- **Rate limiting** – set `RATE_LIMIT_BACKEND=sqlite` and point `RATE_LIMIT_SQLITE_PATH` at a shared persistent volume
  (ReadWriteMany or equivalent). SQLite’s WAL mode (enabled in code) allows safe concurrent access from multiple pods. Ensure
  the underlying storage guarantees POSIX file locking. For environments without a shared filesystem, keep `memory` and use an
  external API gateway or CDN for global rate limiting.
- **Metrics persistence** – provide each replica with the same persistence database if you want a unified dashboard. Mount a
  shared volume for `AI_TICKET_METRICS_DB` or forward events to a separate observability stack (Prometheus, Loki, etc.).
  Without persistence, the dashboard shows per-pod data only while the process is alive.
- **Health checks** – probe `/health` over HTTP. For streaming dashboards, expose `/api/metrics/stream` via sticky sessions or
  ingress strategies that preserve connections to the originating pod.

### Suggested Kubernetes sketch

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-ticket
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-ticket
  template:
    metadata:
      labels:
        app: ai-ticket
    spec:
      containers:
        - name: app
          image: ghcr.io/your-org/ai-ticket:latest
          env:
            - name: RATE_LIMIT_BACKEND
              value: sqlite
            - name: RATE_LIMIT_SQLITE_PATH
              value: /var/lib/ai-ticket/rate-limit.sqlite3
            - name: AI_TICKET_METRICS_DB
              value: /var/lib/ai-ticket/metrics.sqlite3
            - name: TRUST_PROXY_COUNT
              value: "2"
          volumeMounts:
            - name: shared-data
              mountPath: /var/lib/ai-ticket
      volumes:
        - name: shared-data
          persistentVolumeClaim:
            claimName: ai-ticket-shared
```

Attach an ingress controller or service mesh to provide TLS offload and public routing. Ensure the PVC supports multi-writer
access if you expect concurrent pods.

## Operational checklist

- [ ] Decide whether metrics and rate limit data should persist across restarts. If so, enable the SQLite options and mount
      durable storage.
- [ ] Validate TLS certificates and proxy headers for whichever component terminates HTTPS.
- [ ] Confirm that `/metrics` remains reachable for Prometheus scrapers in every topology.
- [ ] For replicated deployments, document how you rotate authentication tokens and propagate the update to all pods.
