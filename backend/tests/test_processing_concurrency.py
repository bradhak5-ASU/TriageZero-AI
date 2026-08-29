import asyncio
import time

from app.services import processing


def test_async_pipeline_does_not_block_event_loop(monkeypatch):
    """A synchronous provider call must not freeze health or read routes."""

    def slow_step(_investigation_id: str, _step_index: int) -> bool:
        time.sleep(0.2)
        return True

    monkeypatch.setattr(processing, "_advance", slow_step)

    async def exercise() -> None:
        started = time.perf_counter()
        task = asyncio.create_task(processing._process_async("INV-CONCURRENCY", 0))
        await asyncio.sleep(0.02)
        event_loop_delay = time.perf_counter() - started

        # If slow_step ran on the event-loop thread this sleep would not resume
        # until roughly 0.2 seconds later.
        assert event_loop_delay < 0.1
        assert not task.done()
        await task

    asyncio.run(exercise())
