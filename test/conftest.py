import asyncio
import gc

import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def cancel_leftover_tasks():
    """Clean up tasks and orphaned coroutines before the loop closes.

    A pending queue.get(), kick waiter or pump task outliving the test
    raises 'Event loop is closed' when garbage collected; the same goes
    for orphaned suspended coroutines finalized after loop close.
    """
    yield
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if not tasks:
        return
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    # finalize orphans while the loop can still run their cleanup; PEP
    # 442 finalization needs a second pass to finish cycles
    gc.collect()
    gc.collect()
