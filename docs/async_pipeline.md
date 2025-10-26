# Asynchronous Inference Pipeline

The asynchronous pipeline orchestrates concurrent inference workloads while
preserving deterministic response ordering.  It wraps the async-aware event
handler introduced in this change-set and provides two primary entry points:

* `AsyncInferencePipeline.run_batch(...)` executes a finite collection of events
  concurrently, returning the responses aligned with the input order.
* `AsyncInferencePipeline.iter_responses(...)` yields `PipelineResult` objects
  as soon as each event finishes processing, enabling reactive streaming to
  downstream consumers.

Both entry points honour the configurable `max_concurrency` parameter which is
implemented using an `asyncio.Semaphore`.  This allows the runtime to saturate
available execution capacity while protecting downstream backends from
unbounded load spikes.  The default concurrency of eight workers can be tuned at
call time to reflect the available CPU cores or GPU workers.

The pipeline composes with the existing synchronous Flask server, CLI tools, and
future FastAPI/TUI frontends through the shared `async_on_event` handler.  It is
safe to embed the pipeline inside bespoke orchestration layers, background
workers, or batch processing jobs.

```python
from ai_ticket import AsyncInferencePipeline

pipeline = AsyncInferencePipeline(max_concurrency=16)
events = [
    {"content": "Tell me a story about concurrency."},
    {"content": "Summarise the async design."},
]
responses = await pipeline.run_batch(events)
```

For streaming scenarios:

```python
async for item in pipeline.iter_responses(events):
    print(item.event, item.response)
```

The asynchronous client cooperatively cancels outstanding backend requests once
any endpoint succeeds, minimising wasted work and ensuring low tail latency.
