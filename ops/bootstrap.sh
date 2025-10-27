#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
ENV_FILE="${PROJECT_ROOT}/.env"

log() {
  echo "[bootstrap] $1"
}

log "Using project root: ${PROJECT_ROOT}"

if [ ! -d "${VENV_DIR}" ]; then
  log "Creating Python virtual environment at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

log "Upgrading pip"
pip install --upgrade pip >/dev/null

log "Installing runtime and development dependencies"
pip install -r "${PROJECT_ROOT}/requirements.txt" -r "${PROJECT_ROOT}/requirements-dev.txt" >/dev/null

if [ ! -f "${ENV_FILE}" ]; then
  log "Creating default .env file"
  cat <<'ENVVARS' > "${ENV_FILE}"
# Runtime configuration for ai-ticket
KOBOLDCPP_API_URL=http://localhost:5001/api
# Telemetry configuration
OTEL_SERVICE_NAME=ai-ticket
# Uncomment and set OTLP exporter endpoint to forward traces
# OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.example.com:4318
# Prometheus scrape configuration
OTEL_PROMETHEUS_HOST=0.0.0.0
OTEL_PROMETHEUS_PORT=9464
ENVVARS
else
  log "Existing .env file detected; leaving in place"
fi

if command -v dotenv >/dev/null 2>&1; then
  log "Validating environment configuration with dotenv"
  dotenv -f "${ENV_FILE}" list >/dev/null
fi

HEALTH_URL="${HEALTHCHECK_URL:-http://localhost:${PORT:-5000}/health}"
if command -v curl >/dev/null 2>&1; then
  log "Attempting health check at ${HEALTH_URL}"
  if curl --fail --silent --max-time 5 "${HEALTH_URL}" >/dev/null; then
    log "Health check succeeded"
  else
    log "Health check unavailable (ensure the server is running)"
  fi
else
  log "curl not available; skipping health check"
fi

log "Bootstrap complete"
