# Testing and Benchmarks

This project uses `pytest` for unit, runtime, and integration level coverage. Development
dependencies (including `pytest`, `httpx`, and supporting plugins) can be installed with:

```bash
pip install -r requirements-dev.txt
```

## Running the automated test suite

```bash
pytest
```

The suite will automatically discover tests in `tests/`, including the end-to-end coverage under
`tests/integration/` which exercises the Flask server via `httpx` against a stubbed backend.

## Lightweight load benchmark

A simple asynchronous load benchmark is available under `tools/bench/load_benchmark.py`. The
benchmark reuses the same event payload fixtures as the tests and can be executed against a running
instance of the Flask app:

```bash
python tools/bench/load_benchmark.py --base-url http://127.0.0.1:5000 --requests 100 --concurrency 16
```

The script reports aggregated status codes along with mean and 95th percentile latencies so you can
quickly gauge how the service behaves under concurrent workloads. Adjust the request count,
concurrency, and timeout flags to suit your environment.
