import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

class SingleDBWriter:
    """
    Asynchronous single DB writer coroutine.
    Consumes transactions from an asyncio.Queue, guaranteeing sequential atomic write
    operations to SQLite with zero lock contention.
    """
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=128)
        self.metrics = {"submitted": 0, "completed": 0, "failed": 0,
                        "queue_wait_ms": 0.0, "transaction_ms": 0.0, "peak_queue": 0}
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._accepting = False
        self._admission_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._accepting = True
        self._worker_task = asyncio.create_task(self._writer_loop())

    async def stop(self) -> None:
        if not self._running:
            return
        # Wait for accepted queue.put calls before draining; reject new writes.
        async with self._admission_lock:
            self._accepting = False
        await self.queue.join()
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def submit(self, write_func: Callable[[AsyncSession], Coroutine[Any, Any, Any]]) -> Any:
        fut = asyncio.get_running_loop().create_future()
        queued_at = time.perf_counter()
        async with self._admission_lock:
            if not self._accepting:
                raise RuntimeError("DB writer is not accepting transactions")
            await self.queue.put((write_func, fut, queued_at))
            self.metrics["submitted"] += 1
            self.metrics["peak_queue"] = max(self.metrics["peak_queue"], self.queue.qsize())
        return await fut

    async def _writer_loop(self) -> None:
        while self._running:
            try:
                item = await self.queue.get()
                if item is None:
                    self.queue.task_done()
                    break
                write_func, fut, queued_at = item
                started = time.perf_counter()
                self.metrics["queue_wait_ms"] += (started - queued_at) * 1000
                try:
                    async with self.db_manager.session_factory() as session:
                        async with session.begin():
                            result = await write_func(session)
                        if not fut.done():
                            fut.set_result(result)
                        self.metrics["completed"] += 1
                except Exception as ex:
                    self.metrics["failed"] += 1
                    logger.error("DB writer transaction failed (%s)", type(ex).__name__)
                    if not fut.done():
                        fut.set_exception(ex)
                finally:
                    self.metrics["transaction_ms"] += (time.perf_counter() - started) * 1000
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Unexpected DB writer failure (%s)", type(e).__name__)
