#!/usr/bin/env python3
"""Lightweight load benchmark for the Flask inference server."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Iterable

import httpx

_DATA_FILE = Path(__file__).resolve().parents[2] / "tests" / "data" / "events" / "chat_messages.json"


def _build_event_payloads(total: int) -> Iterable[dict[str, object]]:
    templates = json.loads(_DATA_FILE.read_text())
    for index in range(total):
        template = templates[index % len(templates)]
        messages = [dict(message) for message in template["messages"]]
        for message in reversed(messages):
            if message.get("role") == "user":
                message["content"] = f"{message['content']} (load-test {index})"
                break
        yield {"content": json.dumps({"messages": messages})}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark the /event endpoint with concurrent requests.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Base URL for the running Flask server.")
    parser.add_argument("--requests", type=int, default=50, help="Total number of requests to issue.")
    parser.add_argument("--concurrency", type=int, default=10, help="Maximum in-flight requests.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds.")
    return parser.parse_args()


async def _run_once(base_url: str, total_requests: int, concurrency: int, timeout: float) -> None:
    if total_requests < 1:
        raise ValueError("total_requests must be >= 1")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    payloads = list(_build_event_payloads(total_requests))
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    status_codes: Counter[int] = Counter()

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        async def _send(index: int) -> None:
            event = payloads[index % len(payloads)]
            async with semaphore:
                start = time.perf_counter()
                response = await client.post("/event", json=event)
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)
                status_codes[response.status_code] += 1

        tasks = [asyncio.create_task(_send(i)) for i in range(total_requests)]
        await asyncio.gather(*tasks)

    if not latencies:
        print("No requests executed.")
        return

    mean_latency = statistics.mean(latencies)
    p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
    success = sum(count for code, count in status_codes.items() if 200 <= code < 300)

    print("=== Load benchmark summary ===")
    print(f"Total requests: {total_requests}")
    print(f"Concurrency: {concurrency}")
    print("Status codes:")
    for code, count in sorted(status_codes.items()):
        print(f"  {code}: {count}")
    print(f"Success rate: {success / total_requests:.0%}")
    print(f"Mean latency: {mean_latency * 1000:.2f} ms")
    print(f"95th percentile latency: {p95_latency * 1000:.2f} ms")


def main() -> None:
    args = _parse_args()
    asyncio.run(_run_once(args.base_url, args.requests, args.concurrency, args.timeout))


if __name__ == "__main__":
    main()
