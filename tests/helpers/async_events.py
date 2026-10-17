"""Task-aware readiness synchronization for concurrent regression tests."""

import asyncio


async def wait_for_task_event[T](task: asyncio.Task[T], event: asyncio.Event) -> None:
    """Wait for readiness, surfacing a finished operation instead of hanging."""
    event_waiter = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait(
            (task, event_waiter), return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            await task
            assert event.is_set(), "operation finished before signalling its event"
        await event_waiter
    finally:
        event_waiter.cancel()
        await asyncio.gather(event_waiter, return_exceptions=True)
