# Operations Runbook

This runbook provides repeatable procedures for operating the AI Ticket service. It
covers telemetry configuration, alert routing, scaling heuristics, and incident
response workflows for both the HTTP surface (`src/ai_ticket/server.py`) and the
asynchronous inference pipeline (`src/ai_ticket/runtime/async_pipeline.py`).

## Telemetry

### Tracing

* The service emits OpenTelemetry spans for HTTP endpoints, pipeline stages, and
  KoboldCPP backend interactions. Spans are produced via the
  [`ai_ticket.telemetry`](../src/ai_ticket/telemetry.py) helper which configures a
  `TracerProvider` with either an OTLP exporter (when
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set) or a console exporter.
* To forward traces to an OpenTelemetry Collector, set:

  ```env
  OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.example.com:4318
  OTEL_SERVICE_NAME=ai-ticket-prod
  ```

### Metrics

* A Prometheus metrics endpoint is exposed by the embedded exporter on
  `0.0.0.0:${OTEL_PROMETHEUS_PORT:-9464}`.
* Key metric families include:
  * `ai_ticket_server_requests_total`, `ai_ticket_server_request_duration_seconds` –
    request volume and latency by route/method/status.
  * `ai_ticket_pipeline_events_total`, `ai_ticket_pipeline_handler_duration_seconds` –
    throughput and handler time for asynchronous batches.
  * `ai_ticket_kobold_requests_total`, `ai_ticket_kobold_request_failures_total` –
    backend fan-out success vs. error rates.
* Sample Prometheus scrape configuration:

  ```yaml
  scrape_configs:
    - job_name: ai-ticket
      static_configs:
        - targets: ["ai-ticket.example.com:9464"]
  ```

## Alerting

| Signal | Trigger | Recommended Action |
|--------|---------|--------------------|
| `ai_ticket_server_request_failures_total` | Increase of >5% over 5 minutes | Inspect recent traces for `/event` failures, verify payload validity. |
| `ai_ticket_kobold_request_failures_total` | Consecutive spikes in `api_server_error` or `api_connection_error` | Confirm KoboldCPP availability, consider failing over to an alternate endpoint. |
| `ai_ticket_pipeline_batch_duration_seconds` | P95 latency > configured SLO | Evaluate queue depth, consider scaling worker count or reducing batch size. |

Prometheus Alertmanager example for request failures:

```yaml
- alert: AiTicketHighErrorRate
  expr: increase(ai_ticket_server_request_failures_total[5m]) > 50
  labels:
    severity: critical
  annotations:
    summary: "AI Ticket server error spike"
    description: "More than 50 failed requests were observed in the last 5 minutes."
```

## Scaling Guidance

1. **HTTP Layer** – Scale horizontally by increasing Gunicorn workers or
   container replicas when P95 `ai_ticket_server_request_duration_seconds` exceeds
   2 seconds with CPU utilisation above 70%.
2. **Async Pipeline** – Adjust `max_concurrency` for `AsyncInferencePipeline`
   consumers based on handler latency. A sustained rise in
   `ai_ticket_pipeline_handler_duration_seconds` suggests backend saturation.
3. **KoboldCPP Backend** – Use the failure metrics to determine whether to add
   replicas or enable caching. Frequent `api_rate_limited` errors indicate the
   need for additional capacity or throttling upstream.

## Incident Response

1. **Triage**
   * Check the health endpoint: `curl -f http://<host>:<port>/health`.
   * Review the most recent traces filtered by `service.name = ai-ticket` and the
     `kobold.get_completion` span to isolate backend issues.
   * Inspect Prometheus metrics for sudden spikes in failure counters or latency.
2. **Mitigation**
   * If KoboldCPP is unavailable, update `KOBOLDCPP_API_URL` to a standby
     instance and redeploy.
   * Temporarily reduce `max_concurrency` for async pipelines to ease backend
     pressure while the incident is investigated.
   * For sustained `/event` failures, enable request logging at DEBUG level and
     capture sample payloads for validation.
3. **Post-incident**
   * Create or update an ADR capturing the root cause and corrective actions.
   * Review alert thresholds to ensure they triggered appropriately.
   * Schedule load testing if bottlenecks emerged during the incident.

## Bootstrap Checklist

Run `ops/bootstrap.sh` on new hosts or developer workstations to set up
dependencies, populate `.env`, and verify health check connectivity.

```bash
./ops/bootstrap.sh
```

The script provisions a virtual environment, installs runtime and development
requirements, and optionally verifies the health endpoint when the service is
running locally.
