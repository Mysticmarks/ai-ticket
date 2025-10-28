# Dashboard runbook

Operational tips for the bundled React dashboard served from `/dashboard`.

## Theming and branding

1. **Runtime accent changes** – operators can drag the hue slider in the dashboard header. The React app stores the selected
   value in `localStorage` under `dashboard-hue` and updates the CSS custom property `--accent-hue` (see
   `src/ai_ticket/ui/src/App.tsx`). The change persists per browser.
2. **Preset defaults** – to ship a different default hue, edit `--accent-hue` in
   `src/ai_ticket/ui/src/styles.css` before building the UI bundle. The CSS variables cascade through all gradient and text
   treatments.
3. **Brand assets** – replace `src/ai_ticket/ui/src/assets/logo.svg` and rebuild (`npm run build`) to apply organisation-specific
   branding. The Flask server automatically serves the compiled bundle from `src/ai_ticket/ui/dist`.
4. **Offline theme injection** – administrators can ship an extra stylesheet under `/static/theme.css` by extending the Flask
   template if deeper theming is required. Keep the CSS variables intact for compatibility with existing components.

## Keyboard shortcuts

The dashboard registers lightweight shortcuts through `useKeyboardShortcuts`:

- `?` toggles the contextual help dialog.
- `R` triggers a manual refresh by calling the REST snapshot endpoint (`/api/metrics/summary`).
- `H` rotates the accent hue in 10-degree increments, wrapping at 360.

The hook intentionally ignores input when focus sits inside form fields. When debugging shortcut behaviour:

1. Confirm the browser did not override the shortcut (e.g., `Ctrl+R` still refreshes the page). Only the bare keypress is
   handled.
2. Open the developer console to check for errors emitted by `useKeyboardShortcuts` or the React event handlers.
3. Verify the root document has focus; embedding the dashboard in an iframe may block the listener unless the iframe is active.

## Troubleshooting metrics SSE or persistence

The dashboard consumes two endpoints (`/api/metrics/summary` and `/api/metrics/stream`) using the hook defined in
`src/ai_ticket/ui/src/hooks/useMetricsStream.ts`. When tiles freeze or data disappears, work through the following checks:

1. **Snapshot health** – run `curl -sf http://<host>:<port>/api/metrics/summary | jq '.'` to ensure the REST endpoint responds.
   A non-200 response indicates the Flask process is unhealthy.
2. **SSE connectivity** – monitor the browser network panel for an open connection to `/api/metrics/stream`. The client falls
   back to polling every 10 seconds if the EventSource errors. If you see repeated reconnects, check reverse proxies for
   timeouts or missing `Cache-Control: no-cache` headers.
3. **Ingress stickiness** – in multi-replica deployments, ensure the ingress uses sticky sessions or consistent hashing. SSE
   requires a long-lived TCP connection to the same pod.
4. **Metrics persistence** – if sparklines reset after restarts, confirm `AI_TICKET_METRICS_DB` points to a writable path. The
   backend initialises `SQLiteMetricsPersistence` (see `src/ai_ticket/observability/persistence.py`) and will emit WAL files in
   the same directory. Mount persistent storage in Docker/Kubernetes.
5. **Retention window** – adjust `AI_TICKET_METRICS_RETENTION_SECONDS` to widen the live window. Values below 60 seconds are
   clamped to one minute inside `metrics_store` (see `src/ai_ticket/observability/metrics.py`).
6. **Log review** – grep the server logs for `metrics_store` messages or SQLite errors. File-lock contention typically signals a
   missing shared volume.

If issues persist, temporarily disable SSE by blocking the stream endpoint; the hook will continue polling the snapshot API so
operators can view data while debugging the streaming path.
